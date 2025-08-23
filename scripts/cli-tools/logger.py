#!/usr/bin/env python3

from loguru import logger
import sys

# ---- Configuration (console only, colored) ----
# ---- Private fuction which will be called once on import ----
# ---- Loguru automatically starts with a “default sink” (pretty logs) ----
# ---- We remove it and replace it with our own customized sink ----
def _configure( level: str = 'INFO' ):
    """
        Configure a single console sink with colors.
        Call once on import; you can re-call with a different level if needed.
    """
    
    # ---- Remove default sink ----
    logger.remove()
    
    # ---- Add our console sink ----
    logger.add(
        sys.stdout,                 # print to console
        level = level,              # default level ( INFO unless changed )
        colorize = True,            # enable colors in terminal
        format = '<green>{time: YYYY-MM-DD HH:mm:ss}</green> | '
                 '<level>{level:<7}</level> | '
                 '<level>{message}</level>', 
        backtrace = False,          # don't show internal stack traces
        diagnose = False,           # don't dump variable state
    )
    
    # ---- Loguru already has built in levels: DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL ----
    # ---- We add two more levels for our case ----
    try:
        logger.level('HEADER')
    except Exception:
        logger.level( 'HEADER', no = 21, color = '<magenta><bold>' )
    
    try:
        logger.level('STEP')
    except Exception:
        logger.level( 'STEP', no = 22, color = '<cyan>' )
   
     
# --- Configure at import so that as soon as we import logger, the console logging is ready ----
_configure()


# ---- Lets create helper functions so that logger module can call them to log in terminal ----
def header( message: str ):
    logger.log( 'HEADER', message )

def info( message: str ):
    logger.info( message )

def step( message: str ):
    logger.log( 'STEP', f'************ {message} ************' )

def status( message: str ):
    logger.info( message )

def success( message: str ):
    logger.success( message )

def warning( message: str ):
    logger.warning( message )

def error( message: str ):
    logger.error( message )
    

# ---- Demo block to show all levels colors ----
if __name__ == '__main__':
    header( "=== DEMO: logger.py ===" )
    step( "CHECK SF CLI" )
    info( "Running `sf --version`" )
    success( "CLI available" )
    step( "AUTH DEV HUB" )
    status( "Checking for existing Dev Hub alias..." )
    warning( "No Dev Hub found, prompting login..." )
    success( "Dev Hub login successful" )
    step( "DEPLOY SOURCE" )
    error( "Source push failed: Missing permission set" )