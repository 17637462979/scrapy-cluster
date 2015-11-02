import time


class BaseMonitor(object):
    '''
    Base monitor for handling incoming requests seen within redis
    These classes have an implied redis_conn variable for manipulating
    a redis connection
    '''
    # override this with your own regex to look for in redis
    regex = None

    def setup(self, settings):
        '''
        Setup the handler

        @param settings: The loaded settings file
        @param redis_conn: The redis connection for further processing
        '''
        if self.regex == None:
            raise NotImplementedError("Please specify a regex for the plugin")

    def handle(self, key, value):
        '''
        Process a valid incoming tuple and handle any logic associated
        with it

        @param @param key: The key that matched the request
        @param value: The value associated with the key
        '''
        raise NotImplementedError("Please implement handle() for your handler class")

    def get_current_time(self):
        '''
        @return: the current time stamp
        '''
        return self._get_current_time()

    def _get_current_time(self):
        '''
        Split this way for unit testing
        '''
        return time.time()

    def _set_logger(self, logger):
        '''
        Set the logger

        @param logger: The LogObject
        '''
        self.logger = logger

    def get_log_dict(self, action, spiderid, appid, uuid=None, crawlid=None):
        '''
        Returns a basic dictionary for logging
        @param action: the action taken by the redis monitor
        @param spiderid: the spider id
        @param appid: the application id
        @param uuid: a unique id of the request
        @param crawlid: a unique crawl id of the request
        '''
        extras = {}
        extras['action'] = action
        extras['spiderid'] = spiderid
        extras['appid'] = appid
        if uuid is not None:
            extras['uuid'] = uuid
        if crawlid is not None:
            extras['crawlid'] = crawlid

        return extras
