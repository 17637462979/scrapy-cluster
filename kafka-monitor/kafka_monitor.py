#!/usr/bin/python

from kafka.client import KafkaClient
from kafka.consumer import SimpleConsumer
from kafka.producer import SimpleProducer
from kafka.common import OffsetOutOfRangeError
from collections import OrderedDict

import time
import json
import sys
import importlib
import argparse

from jsonschema import ValidationError
from jsonschema import Draft4Validator, validators

from utils.log_factory import LogFactory
from utils.settings_wrapper import SettingsWrapper

try:
    import cPickle as pickle
except ImportError:
    import pickle

class KafkaMonitor:

    def __init__(self, settings_name):
        '''
        @param settings_name: the file name
        '''
        self.settings_name = settings_name
        self.wrapper = SettingsWrapper()
        self.logger = None

    def _import_class(self, cl):
        '''
        Imports a class from a string

        @param name: the module and class name in dot notation
        '''
        d = cl.rfind(".")
        classname = cl[d+1:len(cl)]
        m = __import__(cl[0:d], globals(), locals(), [classname])
        return getattr(m, classname)

    def _load_plugins(self):
        '''
        Sets up all plugins, defaults and settings.py
        '''
        plugins = self.settings['PLUGINS']

        self.plugins_dict = {}
        for key in plugins:
            # skip loading the plugin if its value is None
            if plugins[key] is None:
                continue
            # valid plugin, import and setup
            the_class = self._import_class(key)
            instance = the_class()
            instance.setup(self.settings)
            instance._set_logger(self.logger)
            the_schema = None
            with open(self.settings['PLUGIN_DIR'] + instance.schema) as the_file:
                the_schema = json.load(the_file)

            mini = {}
            mini['instance'] = instance
            mini['schema'] = the_schema

            self.plugins_dict[plugins[key]] = mini

        self.plugins_dict = OrderedDict(sorted(self.plugins_dict.items(),
                                                key=lambda t: t[0]))

    def setup(self, level=None, log_file=None,
        json=None):
        '''
        Load everything up. Note that any arg here will override both
        default and custom settings

        @param level: the log level
        @param log_file: boolean t/f whether to log to a file, else stdout
        @param json: boolean t/f whether to write the logs in json
        '''
        self.settings = self.wrapper.load(self.settings_name)
        self.kafka_conn = KafkaClient(self.settings['KAFKA_HOSTS'])
        self.kafka_conn.ensure_topic_exists(
                self.settings['KAFKA_INCOMING_TOPIC'])
        self.consumer = SimpleConsumer(self.kafka_conn,
                                  self.settings['KAFKA_GROUP'],
                                  self.settings['KAFKA_INCOMING_TOPIC'],
                                  auto_commit=True,
                                  iter_timeout=1.0)

        self.validator = self.extend_with_default(Draft4Validator)

        my_level = level if level else self.settings['LOG_LEVEL']
        # negate because logger wants True for std out
        my_output = not log_file if log_file else self.settings['LOG_STDOUT']
        my_json = json if json else self.settings['LOG_JSON']
        self.logger = LogFactory.get_instance(json=my_json,
            stdout=my_output, level=my_level)

        self._load_plugins()

    def extend_with_default(self, validator_class):
        '''
        Method to add default fields to our schema validation
        ( From the docs )
        '''
        validate_properties = validator_class.VALIDATORS["properties"]

        def set_defaults(validator, properties, instance, schema):
            for error in validate_properties(
                validator, properties, instance, schema,
            ):
                yield error

            for property, subschema in properties.iteritems():
                if "default" in subschema:
                    instance.setdefault(property, subschema["default"])

        return validators.extend(
            validator_class, {"properties" : set_defaults},
        )

    def _main_loop(self):
        '''
        Continuous loop that reads from a kafka topic and tries to validate
        incoming messages
        '''
        while True:
            self._process_messages()
            time.sleep(.01)

    def _process_messages(self):
        try:
            for message in self.consumer.get_messages():
                if message is None:
                    self.logger.debug("no log message")
                    break
                try:
                    the_dict = json.loads(message.message.value)

                    found_plugin = False
                    for key in self.plugins_dict:
                        obj = self.plugins_dict[key]
                        instance = obj['instance']
                        schema = obj['schema']

                        try:
                            self.validator(schema).validate(the_dict)
                            found_plugin = True
                            ret = instance.handle(the_dict)
                            # break if nothing is returned
                            if ret is None:
                                break
                        except ValidationError as ex:
                            pass
                    if not found_plugin:
                        self.logger.warn("Did not find schema to validate "\
                            "request")

                except ValueError:
                    self.logger.warn("Bad JSON recieved")
        except OffsetOutOfRangeError:
            # consumer has no idea where they are
            self.consumer.seek(0,2)
            self.logger.error("Kafka offset out of range error")

    def run(self):
        '''
        Set up and run
        '''
        self._main_loop()

    def feed(self, json_item):
        '''
        Feeds a json item into the Kafka topic

        @param json_item: The loaded json object
        '''
        self.kafka_conn = KafkaClient(self.settings['KAFKA_HOSTS'])
        topic = self.settings['KAFKA_INCOMING_TOPIC']
        producer = SimpleProducer(self.kafka_conn)
        if not self.logger.json:
            self.logger.info('Feeding JSON into {0}\n{1}'.format(
                topic, json.dumps(json_item, indent=4)))
        else:
            self.logger.info('Feeding JSON into {0}\n'.format(topic),
                extra={'value':json_item})
        self.kafka_conn.ensure_topic_exists(topic)
        producer.send_messages(topic, json.dumps(json_item))
        self.logger.info("Done feeding request.")

def main():
    parser = argparse.ArgumentParser(
        description='Kafka Monitor: Monitors and validates incoming Kafka ' \
            'topic cluster requests\n',
        usage='\nkafka_monitor.py -r [-h] [-s SETTINGS]\n' \
                '    [-ll {DEBUG,INFO,WARNING,CRITICAL,ERROR}]\n' \
                '    [-lf] [-lj]\n' \
                '    Run the Kafka Monitor continuously\n\n' \
                'kafka-monitor -f \'{"my_json":"value"}\' [-h] [-s SETTINGS]'\
                '\n    [-ll {DEBUG,INFO,WARNING,CRITICAL,ERROR}]\n' \
                '    [-lf] [-lj]\n' \
                '    Feed a formatted json request into kafka\n\n' \
                'NOTE: Command line logging arguments take precedence ' \
                'over settings')

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-r', '--run', action='store_const', const=True,
        help='Run the Kafka Monitor')
    group.add_argument('-f', '--feed', action='store',
        help='Feed a JSON formatted request to be sent to Kafka')

    parser.add_argument('-s', '--settings', action='store', required=False,
        help="The settings file to read from", default="settings.py")
    parser.add_argument('-ll', '--log-level', action='store', required=False,
        help="The log level", default=None,
        choices=['DEBUG', 'INFO', 'WARNING', 'CRITICAL', 'ERROR'])
    parser.add_argument('-lf', '--log-file', action='store_const',
        required=False, const=True, default=None,
        help='Log the output to the file specified in settings.py. Otherwise '\
        'logs to stdout')
    parser.add_argument('-lj', '--log-json', action='store_const',
        required=False, const=True, default=None,
        help="Log the data in JSON format")
    args = vars(parser.parse_args())

    kafka_monitor = KafkaMonitor(args['settings'])
    kafka_monitor.setup(level=args['log_level'], log_file=args['log_file'],
        json=args['log_json'])

    if args['run']:
        pass
        return kafka_monitor.run()
    if args['feed']:
        json_req = args['feed']
        try:
            parsed = json.loads(json_req)
        except ValueError:
            kafka_monitor.logger.info("JSON failed to parse")
            return 1
        else:
            return kafka_monitor.feed(parsed)


if __name__ == "__main__":
    sys.exit(main())
