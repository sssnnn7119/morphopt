import logging
def log_file():
    log_file = 'testfun.log'
    handler_test = logging.FileHandler(log_file) # stdout to file
    handler_control = logging.StreamHandler()    # stdout to console
    handler_test.setLevel('ERROR')               # 设置ERROR级别
    handler_control.setLevel('INFO')             # 设置INFO级别

    selfdef_fmt = '%(asctime)s - %(funcName)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(selfdef_fmt)
    handler_test.setFormatter(formatter)
    handler_control.setFormatter(formatter)

    logger = logging.getLogger('updateSecurity')
    logging.basicConfig(level=logging.DEBUG)  # 设置日志级别

    logger.addHandler(handler_test)    #添加handler
    logger.addHandler(handler_control)
    logger.info('info,一般的信息输出')
    logger.warning('waring，用来用来打印警告信息')
    logger.error('error，一般用来打印一些错误信息')
    logger.critical('critical，用来打印一些致命的错误信息，等级最高')

log_file()