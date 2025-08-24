#!/usr/bin/env python3

from pathlib import Path
import subprocess
import sys
import argparse

# --- Loguru based module for logging in terminal ---
import logger

# --- Paths relative to this file ---
CLI_TOOLS_DIR       = Path( __file__ ).resolve().parent
SCRIPT_DIR          = CLI_TOOLS_DIR.parent
REPO_ROOT           = SCRIPT_DIR.parent
SFDX_PROJECT_DIR    = REPO_ROOT
SCRATCH_DEF         = SFDX_PROJECT_DIR / 'config' / 'project-scratch-def.json'
SOURCE_DIR          = SFDX_PROJECT_DIR / 'force-app'

# --- 
def run_subprocess( cmd_list: list[str], passthrough: bool = False, cwd: str | None = None ) -> str | None:
    """
        Run a shell command.
        
        Args:
            cmd_list => ( list[str] ): Gets all commands in a list that needs to run in terminal
            passthrough => ( Boolean, optional ): Streams the output live ( For Interactive steps )
                           Else captures and returns stdout
        
        Returns:
            str | None: _description_
    """
    cmd_str = ' '.join( cmd_list )
    logger.status( f'$ {cmd_str}' )
    
    try:
        if passthrough:
            subprocess.run( cmd_list, check = True, cwd = cwd )
            logger.success( cmd_str )
            return None
        
        out = subprocess.run(
            cmd_list, check = True, 
            stdout = subprocess.PIPE, 
            stderr = subprocess.STDOUT, 
            text = True, 
            cwd = cwd
        )
        logger.success( cmd_str )
        return out.stdout
    
    except subprocess.CalledProcessError as ex:
        logger.error( f'FAILED: {cmd_str}' )
        
        if hasattr( ex, 'stdout' ) and ex.stdout:
            print( ex.stdout )
        sys.exit(1)
        
        
def norm_env( name: str ) -> str:
    return name.strip().lower().replace(' ', '-')


def parse_args():
    parser = argparse.ArgumentParser( description = 'Create and prep a scratch org (sf CLI)' )
    
    parser.add_argument( '-e', '--environment', 
        required = True, 
        help = 'Env/branch alias, e.g. fe-hello. Name of environment or branch separated by a - ' 
    )
    parser.add_argument( '--review', action = 'store_true', help = 'Activates review mode' )
    parser.add_argument( '--devhub-url', default = 'https://login.salesforce.com', help = 'Dev Hub login URL' )
    parser.add_argument( '--force-devhub-connection', action = 'store_true', help = 'Force re-auth to Dev Hub' )
    parser.add_argument( '--preview', action = 'store_true', help = 'Try seasonal Preview release (if supported)' )
    
    return parser.parse_args()


def git_prepare_branch( environment_name: str, review_mode: bool ):
    logger.step( 'GITHUB' )
    logger.status( 'Checking out `main` branch and getting latest update from Github ...' )
    
    run_subprocess( ['git', 'checkout', 'main'], passthrough = True )
    run_subprocess( ['git', 'pull', 'origin', 'main'], passthrough = True )
    
    if not review_mode:
        logger.status( 'Create and push feature branch from `main`' )
        logger.status( 'Creating new development branch ...' )
        
        run_subprocess( ['git', 'checkout', '-b', environment_name, 'main' ], passthrough = True )
    else:
        logger.status( '--- Review mode ---' )
        logger.status('Checking out development branch ...')
        
        # --- Check if the branch exists locally ---
        existing_git_branch = run_subprocess( ['git', 'branch', '--list', environment_name] ) or ''
        if environment_name in ( existing_git_branch or '' ):
            logger.status( 'Deleting local branch ...' )
            run_subprocess( ['git', 'branch', '-D', environment_name], passthrough = True )
            
        run_subprocess( ['git', 'checkout', '-b', environment_name, f'origin/{environment_name}'], passthrough = True )
             

def check_sfcli_exists():
    logger.step( 'CHECK SF CLI' )
    logger.status( 'Validating SFDC Binary is available ...' )
    
    run_subprocess( ['sf', '--version'] )


def login_devhub( devhub_url: str, force_auth: bool ):
    logger.step( 'CHECK SFDX LOGIN STATUS' )
    logger.status( 'Checking SFDX Devhub login status ...' )
    logger.status( 'Retrieving list of Salesforce Orgs ...' )
    logger.step( 'AUTHORIZING DEV HUB' )
    orgs = run_subprocess( ['sf', 'org', 'list'] ) or ''
    
    if force_auth or ('DevHub' not in orgs):
        logger.status( 'Logging into Dev Hub ...' )
        run_subprocess(
            [
                'sf', 'org', 'login', 'web', 
                '--alias', 'DevHub', 
                '--set-default-dev-hub', 
                '--instance-url', devhub_url
            ],
            passthrough = True
        )
    else:
        logger.status( 'Using existing Dev Hub alias `DevHub`.' )
    
    # --- Verify if now devhub is existing ---
    orgs = run_subprocess( ['sf', 'org', 'list'] ) or ''
    
    if 'DevHub' not in orgs:
        logger.error( 'Devhub alias not found after login' )
        sys.exit(1)
        
        
def create_scratch_org( environment_name: str, review_mode: bool, preview_mode: bool ):
    logger.step( 'CREATE SCRATCH ORG' )
    logger.status( 'Attempting to deploy new Scratch Org...' )
    
    if not SCRATCH_DEF.exists():
        logger.error( f'Scratch definition not found: {SCRATCH_DEF}' )
        sys.exit(1)
    
    duration_in_days = '7' if review_mode else '30'
    scratch_org_creation_cmd = [
        'sf', 'org', 'create', 'scratch', 
        '--definition-file', str( SCRATCH_DEF ),
        '--alias', environment_name,
        '--duration-days', duration_in_days,
        '--set-default'
    ]
    
    if preview_mode:
        scratch_org_creation_cmd += ['--release', 'Preview']
        
    run_subprocess( scratch_org_creation_cmd, passthrough = True )
    

def deploy_source_metadata( environment_name: str ):
    logger.step( 'DEPLOY SOURCE' )
    
    if not SFDX_PROJECT_DIR.exists():
        logger.error( f'Project directory not found: {SFDX_PROJECT_DIR}' )
        sys.exit(1)
    
    logger.status( 'Deploying force-app to scratch org ...' )
    
    run_subprocess(
        [
            'sf', 'project', 'deploy', 'start',
            '--target-org', environment_name,
            '--source-dir', str( SOURCE_DIR )
        ],
        passthrough = True, 
        cwd = str( SFDX_PROJECT_DIR )   # Ensures that the sfdx runs in correct directory
    )
    
    
def open_scratch_org( environment_name: str, review_mode: bool ):
    logger.step( 'OPEN ORG' )
    logger.status( 'Opening the scratch org in your browser ...' )
    run_subprocess( ['sf', 'org', 'open', '--target-org', environment_name], passthrough = True )
    

def main():
    logger.header( 'Scratch Org Script' )

    # parse args
    args = parse_args()

    # join multi-word env names into one string
    raw_env = args.environment
    env = norm_env( raw_env )

    # add -review suffix if in review mode
    scratch_alias = f'{env}-review' if args.review else env

    logger.status( f'Environment (raw): {raw_env}' )
    logger.status( f'Normalized alias: {scratch_alias}' )

    # 1. Git setup
    git_prepare_branch( env, args.review )
    logger.success( 'Git branch ready.' )

    # 2. SF CLI check + Dev Hub login
    check_sfcli_exists()
    login_devhub( args.devhub_url, args.force_devhub_connection )
    logger.success( 'Dev Hub ready.' )

    # 3. Scratch org creation
    create_scratch_org( scratch_alias, args.review, args.preview )
    logger.success( 'Scratch org created.' )

    # 4. Push/deploy source
    deploy_source_metadata( scratch_alias )
    logger.success( 'Source deployed.' )

    # 5. Open org
    open_scratch_org( scratch_alias, args.review )
    logger.success( 'All done. Happy building!' )
    
    
if __name__ == '__main__':
    main()