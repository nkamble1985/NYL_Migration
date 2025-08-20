#Install required packages:
#pip install boto3 pyodbc
#Configure your ODBC driver for SQL Server on the machine running this script.

import boto3
import pyodbc
from datetime import datetime, timedelta
import logging

# Setup logging
logging.basicConfig(filename='C:/Logs/Log_ResearchDWH_Holdings_Stat.txt',
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

SUMMARY_LOG = 'C:/Logs/EXEC_HoldingsSummaryLog.txt'
JOB_NAME = "ResearchDWH_Holdings_Stat"

AWS_REGION = "us-east-1"
SENDER = "sender@example.com"
RECIPIENTS = ["munawar.gani@ap.linedata.com", "nitin.kamble@ap.linedata.com"]

# SQL Server connection details
SERVER = "inviiqresearch-sqlserver-standard-dev.ckryme4eosdx.us-east-1.rds.amazonaws.com"
DATABASE = "ResearchDWH"
USERNAME = "stonebranchuser"
PASSWORD = "Welcome@2025"
DRIVER = "{ODBC Driver 18 for SQL Server}"  # Adjust if needed

QUERY = "EXEC sp_getHoldingsForAlert"

def get_last_business_day(date=None):
    if date is None:
        date = datetime.today()
    last_business_day = date - timedelta(days=1)
    while last_business_day.weekday() > 4:  # 0=Monday, 6=Sunday
        last_business_day -= timedelta(days=1)
    return last_business_day.strftime("%Y%m%d")

def fetch_data():
    conn_str = f"DRIVER={DRIVER};SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};TrustServerCertificate=Yes"
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.execute(QUERY)
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        return columns, rows

def build_html_table(columns, rows):
    table = """<html>
    <style>
    th, td {border: 2px solid black; padding: 5px; border-collapse: collapse;}
    table {border-collapse: collapse;}
    </style>
    <body>
    <b>ResearchDWH - Holdings Refresh Counts</b><br>
    <table>
    <tr>"""
    for col in columns:
        table += f"<th>{col}</th>"
    table += "</tr>"
    
    for row in rows:
        table += "<tr>"
        for cell in row:
            table += f"<td>{cell}</td>"
        table += "</tr>"
    table += "</table></body></html>"
    return table

def send_email(html_body, subject):
    ses_client = boto3.client('ses', region_name=AWS_REGION)
    try:
        response = ses_client.send_email(
            Source=SENDER,
            Destination={'ToAddresses': RECIPIENTS},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {'Html': {'Data': html_body, 'Charset': 'UTF-8'}}
            }
        )
        logging.info(f"Email sent! Message ID: {response['MessageId']}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def main():
    logging.info("Job Start ***********************************************************")
    with open(SUMMARY_LOG, 'a') as summary_log:
        summary_log.write(f"{datetime.now():%m/%d/%Y %H:%M:%S} - {JOB_NAME} Log Starts ------------------------------------------------------------------------------------------------------------------------------\n")

    try:
        run_date = get_last_business_day()
        logging.info(f"Run Date --> {run_date}")

        columns, rows = fetch_data()
        html_table = build_html_table(columns, rows)
        
        send_email(html_table, "Holdings Data Alert")

    except Exception as ex:
        logging.error(f"Exception occurred: {ex}")
        with open(SUMMARY_LOG, 'a') as summary_log:
            summary_log.write(f"{datetime.now():%m/%d/%Y %H:%M:%S} - Exception Message: {ex}\n")

    logging.info("Job End ***********************************************************")
    with open(SUMMARY_LOG, 'a') as summary_log:
        summary_log.write(f"{datetime.now():%m/%d/%Y %H:%M:%S} - {JOB_NAME} Log Ends ------------------------------------------------------------------------------------------------------------------------------\n")

if __name__ == "__main__":
    main()
