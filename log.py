import sys
import logging
import logging.handlers

class log:
    
    # Verbosity levels (1-5)
    CRITICAL = 1
    ERROR    = 2
    WARN     = 3
    INFO     = 4
    DEBUG    = 5
    
    def __init__(self, identifier='', verbosity = 3, log_type='syslog', log_address='/dev/log', log_port=514):
        self._identifier  = identifier
        self._type      = log_type
        self._address   = log_address
        self._port      = log_port
        self.set_verbosity(verbosity)
        l = False
        if log_type == 'stdout':
            l = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            l.setFormatter(formatter)
        elif log_type == 'stderr':
            l = logging.StreamHandler(sys.stderr)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            l.setFormatter(formatter)
        elif log_type == 'syslog':
            if log_address == '/dev/log':
                l = logging.handlers.SysLogHandler(address=log_address, facility='daemon')
            else:
                l = logging.handlers.SysLogHandler(address=(log_address, log_port), facility='daemon')
            formatter = logging.Formatter('%(name)s: %(message)s')
            l.setFormatter(formatter)
        if not l:
            print(f'can not set logger {log_type}')
            raise ValueError
        self._logger = logging.getLogger(self._identifier)
        self._logger.setLevel(self.level_to_category(self._verbosity))   
        if self._logger.handlers:
            # remove previous handler
            self._logger.handlers.pop()
        self._logger.addHandler(l)

    def __repr__(self):
        return f'log({self._identifier}, {self._verbosity}, {self._type}, {self._address}, {self._port}'
    
    def level_to_category(self, level):
        if level == 1:
            return logging.CRITICAL
        elif level == 2:
            return logging.ERROR
        elif level == 3:
            return logging.WARN
        elif level == 4:
            return logging.INFO
        elif level == 5:
            return logging.DEBUG
        else:
            return logging.NOTSET

    def logMsg (self, msg, level = 3, cat = None):
        # Only write to log if level <= verbosity
        if level <= self._verbosity:
            self._logger.log(self.level_to_category(level), msg)
            
    def set_verbosity(self, verbosity):
        if verbosity < 1:
            verbosity = 1
        if verbosity > 5:
            verbosity = 5
        self._verbosity = verbosity
