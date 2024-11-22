import os, re, logging

from jira import JIRA
import pandas as pd
import unicodedata
from datetime import datetime

# GCP
from google.oauth2 import service_account
from google.cloud import bigquery
import google.auth
import google.cloud.logging


#----------------------------
# Context
#----------------------------

JIRA_URL = "https://jira.gouv.nc"
JIRA_PROJECT = "" # ex PSPC

# PROD
GCP_PROJECT_ID = "" # ex prj-davar-p-bq-a01c
BQ_DATASET = "" # ex pspc

#----------------------------
# auth
#----------------------------

# jira
JIRA_TOKEN = os.environ['JIRA_TOKEN']
if not JIRA_TOKEN:
    raise ValueError("JIRA_TOKEN is not set in the environment.")

# GCP
cred_file = '' # ex: prj-davar-p-bq-a01c-c04f4c56dc89.json
env_local = os.path.exists(cred_file)
# Authenticate google drive and bigquery APIs using credentials.
SCOPES = [ 'https://www.googleapis.com/auth/bigquery']

if env_local:
    creds = service_account.Credentials.from_service_account_file(cred_file)
else:
    if not os.environ['GOOGLE_APPLICATION_CREDENTIALS']:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS is not set in the environment.")
    creds, _ = google.auth.default() # from env var GOOGLE_APPLICATION_CREDENTIALS 

# retrive credentials for scopes defined.
scoped_credentials = creds.with_scopes(SCOPES)

#----------------------------
# logging
#----------------------------

if not env_local:
    logging.basicConfig(level=logging.INFO)
    log_client = google.cloud.logging.Client()

    # Retrieves a Cloud Logging handler based on the environment
    # you're running in and integrates the handler with the
    # Python logging module. By default this captures all logs
    # at INFO level and higher
    log_client.setup_logging()
else:
    logging.basicConfig(level=logging.DEBUG) # NOTSET DEBUG INFO WARNING ERROR CRITICAL

#----------------------------
# Clients
#----------------------------

bq_client = bigquery.Client(credentials=scoped_credentials)
jira = JIRA(server=JIRA_URL, token_auth=JIRA_TOKEN)

#----------------------------
# Fonctions
#----------------------------

def remove_accents(input_str):
    # Décomposer les caractères Unicode en leurs composants de base
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    # Filtrer les caractères de type "Mn" (marques non espacées, c'est-à-dire les accents)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def to_bigquery_name(field_name):
    # Enlever les accents
    field_name = remove_accents(field_name)
    # Remplacer les caractères non alphanumériques par des underscores
    clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', field_name)
    # S'assurer que le nom commence par une lettre ou un underscore
    if not clean_name[0].isalpha() and clean_name[0] != '_':
        clean_name = '_' + clean_name
    # Limiter la longueur du nom à 128 caractères, comme requis par BigQuery
    return clean_name[:128]

def get_fields_map(jira):
    # map des custom fields avec les noms affichés
    jira_fields = jira.fields()
    # field_mapping = {field['name']: field['id'] for field in jira_fields}
    field_mapping = {field['id']: to_bigquery_name(field['name']) for field in jira_fields}
    return field_mapping

def fetch_all_issues(client, jql_query, max_results=100):
    logging.info('Début récolte des issues')
    all_issues = []
    start_at = 0

    while True:
        issues = client.search_issues(jql_query, startAt=start_at, maxResults=max_results, fields='*all')
        if not issues:
            break
        all_issues.extend(issues)
        start_at += max_results
        if len(all_issues) % 5000 == 0:
            logging.info(f'{len(all_issues)} issues récoltées jusqu\'à présent.')

    logging.info(f'Fin de la récolte des issues. Total : {len(all_issues)} issues récupérées.')

    return all_issues

def cast_value(value):
    if isinstance(value, list):
        value = ', '.join([cast_value(v) for v in value])
    else:
        value = str(value)
    return value

exclusion_keys = [
    # 'customfield_39178', # champ html
    # 'aggregateprogress', # objet jira.resources.PropertyHolder
    # 'progress', # objet jira.resources.PropertyHolder
    # 'worklog', # objet jira.resources.PropertyHolder
    # 'customfield_38562', # champ html
    # 'customfield_38962', # champ html
    # 'watches',
    # 'customfield_39023', # champ html
    # 'customfield_39024', # champ html
    # 'customfield_38574', # champ html
    # 'customfield_38575', # champ html
    # 'rank',
    # 'customfield_38580', # champ html
    # 'customfield_38583', # champ html
    # 'customfield_38981', # champ html
    # 'description', # pas dans le cdc
    # 'timetracking', # objet JIRA TimeTracking
    # 'comment'
    ]

def load_to_bq(client, df, table_name): 
   # Charger les données dans BigQuery
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    destination = f"{GCP_PROJECT_ID}.{BQ_DATASET}.{table_name}"
    job = client.load_table_from_dataframe(df, destination, job_config=job_config)
    job.result()  # Attendre la fin du job

    logging.info(f"Les données pour le type d'issue '{table_name}' ont été insérées avec succès.")

def create_df(issues, field_mapping):
        data = []
        for issue in issues:
            row = {}
            row['jira'] = issue.key
            for key, value in issue.fields.__dict__.items():
                if key not in exclusion_keys:
                    if key != 'parent':
                        row_key = field_mapping[key]
                    else:
                        row_key = key
                    row_value = cast_value(value)

                    row[row_key] = row_value

            data.append(row)
                
        return pd.DataFrame(data)

def merge_tables(bq_client, target, source):
    delete_query  = f"""
    DELETE FROM `{GCP_PROJECT_ID}.{BQ_DATASET}.{target}`
    WHERE jira IN (
    SELECT jira FROM `{GCP_PROJECT_ID}.{BQ_DATASET}.{source}`
    )
    """
    bq_client.query(delete_query )
    insert_query = f"""
    INSERT INTO `{GCP_PROJECT_ID}.{BQ_DATASET}.{target}`
    SELECT * FROM `{GCP_PROJECT_ID}.{BQ_DATASET}.{source}`
    """
    bq_client.query(insert_query)

    bq_client.delete_table(f'{GCP_PROJECT_ID}.{BQ_DATASET}.{source}')
    logging.info(f"Table temporaire {source} supprimée.")

def get_last_update_date(bq_client, table_name):
    try:
        query = f"SELECT max(Mise_a_jour) last_update FROM `{GCP_PROJECT_ID}.{BQ_DATASET}.{table_name}`"
        query_job = bq_client.query(query)
        
        for row in query_job.result():
            last_update = row.last_update

        if last_update:
            if isinstance(last_update, str):
                # Si c'est une chaîne, convertir en objet datetime
                last_update = datetime.strptime(last_update, '%Y-%m-%dT%H:%M:%S.%f%z')
            
            # Convertir au format Jira
            jira_format_date = last_update.strftime('%Y/%m/%d %H:%M')
            logging.debug(f"Date formatée pour Jira: {jira_format_date}")
        else:
            logging.warning("Aucune date récupérée")
            return None

        return jira_format_date
    
    except Exception as e:
        logging.error(f"Une erreur s'est produite : {e}")
        
        return None

#----------------------------
# Fonction principale
#----------------------------

def jira_to_bq():

    field_mapping = get_fields_map(jira)
    pj_issues_types = jira.issue_types_for_project(projectIdOrKey=JIRA_PROJECT)

    for issue_type in pj_issues_types:

        logging.info(f"Traitement de {issue_type.name}")
        table_name = to_bigquery_name(issue_type.name)

        jira_format_date = get_last_update_date(bq_client, table_name)
        
        jql_query = f'project={JIRA_PROJECT} AND issuetype="{issue_type.name}"'
        
        # si on a une date d'update on traite le différentiel, sinon on crée une table avec toutes les issues
        if jira_format_date:
            jql_query = jql_query +  f' AND updated >= "{jira_format_date}"'
            initial_table = table_name
            table_name = '_tmp_' + table_name
        
        try:    
            issues = fetch_all_issues(jira, jql_query)
            
            df = create_df(issues, field_mapping)

            if not df.empty:
                load_to_bq(bq_client, df, table_name)

                # traitement du différentiel
                if jira_format_date:
                    merge_tables(bq_client, initial_table, table_name)

        except Exception as e:
            logging.error(f"Erreur lors du traitement de l'issue type {issue_type.name}: {e}")
            continue

    return "ok"

if __name__ == "__main__":
    jira_to_bq()
