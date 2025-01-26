from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import List, Dict
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# JSON config approach
SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": os.getenv('GOOGLE_PROJECT_ID'),
    "private_key_id": os.getenv('GOOGLE_PRIVATE_KEY_ID'),
    "private_key": os.getenv('GOOGLE_PRIVATE_KEY'),
    "client_email": os.getenv('GOOGLE_CLIENT_EMAIL'),
    "client_id": os.getenv('GOOGLE_CLIENT_ID'),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('GOOGLE_CLIENT_EMAIL').replace('@', '%40')}"
}


def list_unread_emails() -> List[Dict]:
    """
    Lists unread emails from Gmail inbox using service account credentials.
    Returns list of dicts with email details.
    """
    # File path approach
    # credentials = service_account.Credentials.from_service_account_file(
    #     CREDENTIALS_FILE,
    #     scopes=['https://www.googleapis.com/auth/gmail.readonly']
    # )
    
    # JSON config approach
    credentials = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO,
        scopes=['https://www.googleapis.com/auth/gmail.readonly']
    )
    
    delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
    
    service = build('gmail', 'v1', credentials=delegated_credentials)
    
    results = service.users().messages().list(
        userId='me',
        q='is:unread',
        labelIds=['INBOX'],
        maxResults=10
    ).execute()

    messages = results.get('messages', [])
    emails = []
    
    for message in messages:
        msg = service.users().messages().get(
            userId='me', 
            id=message['id'],
            format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']
        ).execute()

        headers = msg['payload']['headers']
        email_data = {
            'id': msg['id'],
            'date': next(h['value'] for h in headers if h['name'] == 'Date'),
            'from': next(h['value'] for h in headers if h['name'] == 'From'),
            'subject': next(h['value'] for h in headers if h['name'] == 'Subject'),
            'has_attachments': bool(msg['payload'].get('parts', []))
        }
        emails.append(email_data)
        
    return emails

if __name__ == "__main__":
    try:
        emails = list_unread_emails()
        for email in emails:
            print(f"\nFrom: {email['from']}")
            print(f"Subject: {email['subject']}")
            print(f"Date: {email['date']}")
            print(f"Has Attachments: {email['has_attachments']}")
            print(f"ID: {email['id']}")
            print("-" * 50)
    except Exception as e:
        print(f"Error: {str(e)}")
