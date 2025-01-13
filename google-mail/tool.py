from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import List, Dict
import os
from schema import Schema, Literal
from griptape.artifacts import ListArtifact, JsonArtifact
from griptape.tools import BaseTool
from griptape.utils.decorators import activity
from email.mime.text import MIMEText
import base64

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

class GmailTool(BaseTool):
    @activity(
        config={
            "description": "Lists unread emails from Gmail inbox using service account credentials",
            "schema": Schema({
                Literal(
                    "userId",
                    description="Gmail user ID, usually 'me' for authenticated user"
                ): str,
                Literal(
                    "q",
                    description="Gmail search query, e.g. 'is:unread'"
                ): str,
                Literal(
                    "labelIds",
                    description="List of Gmail label IDs to filter by"
                ): list,
                Literal(
                    "maxResults",
                    description="Maximum number of emails to return"
                ): int
            })
        }
    )
    def list_unread_emails(self, params: dict) -> ListArtifact:
        """Lists unread emails from Gmail inbox using service account credentials."""
        credentials = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO,
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        
        delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
        
        service = build('gmail', 'v1', credentials=delegated_credentials)
        
        results = service.users().messages().list(
            userId=params["values"]["userId"],
            q=params["values"]["q"],
            labelIds=params["values"]["labelIds"],
            maxResults=params["values"]["maxResults"]
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
            emails.append(JsonArtifact(email_data))
            
        return ListArtifact(emails)

    @activity(
        config={
            "description": "Creates a draft email in Gmail using service account credentials",
            "schema": Schema({
                Literal(
                    "userId",
                    description="Gmail user ID, usually 'me' for authenticated user"
                ): str,
                Literal(
                    "to",
                    description="Recipient email address"
                ): str,
                Literal(
                    "subject",
                    description="Email subject"
                ): str,
                Literal(
                    "body",
                    description="Email body content"
                ): str,
                Literal(
                    "cc",
                    description="CC recipients (optional)"
                ): str | None,
                Literal(
                    "bcc",
                    description="BCC recipients (optional)"
                ): str | None
            })
        }
    )
    def create_draft_email(self, params: dict) -> JsonArtifact:
        """Creates a draft email in Gmail using service account credentials."""
        credentials = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO,
            scopes=['https://www.googleapis.com/auth/gmail.compose']
        )
        
        delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
        service = build('gmail', 'v1', credentials=delegated_credentials)

        message = MIMEText(params["values"]["body"])
        message['to'] = params["values"]["to"]
        message['subject'] = params["values"]["subject"]
        
        if params["values"].get("cc"):
            message['cc'] = params["values"]["cc"]
        if params["values"].get("bcc"):
            message['bcc'] = params["values"]["bcc"]
            
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        draft = service.users().drafts().create(
            userId=params["values"]["userId"],
            body={
                'message': {
                    'raw': encoded_message
                }
            }
        ).execute()
        
        return JsonArtifact({
            'id': draft['id'],
            'message': draft['message']
        })

    @activity(
        config={
            "description": "Sends an existing draft email",
            "schema": Schema({
                Literal(
                    "userId",
                    description="Gmail user ID, usually 'me' for authenticated user"
                ): str,
                Literal(
                    "draftId",
                    description="ID of the draft to send"
                ): str
            })
        }
    )
    def send_draft_email(self, params: dict) -> JsonArtifact:
        """Sends an existing draft email."""
        credentials = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO,
            scopes=['https://www.googleapis.com/auth/gmail.compose']
        )
        
        delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
        service = build('gmail', 'v1', credentials=delegated_credentials)
        
        sent_message = service.users().drafts().send(
            userId=params["values"]["userId"],
            body={'id': params["values"]["draftId"]}
        ).execute()
        
        return JsonArtifact({
            'id': sent_message['id'],
            'labelIds': sent_message['labelIds'],
            'threadId': sent_message['threadId']
        })

    @activity(
        config={
            "description": "Deletes an existing draft email",
            "schema": Schema({
                Literal(
                    "userId",
                    description="Gmail user ID, usually 'me' for authenticated user"
                ): str,
                Literal(
                    "draftId",
                    description="ID of the draft to delete"
                ): str
            })
        }
    )
    def delete_draft_email(self, params: dict) -> JsonArtifact:
        """Deletes an existing draft email."""
        credentials = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO,
            scopes=['https://www.googleapis.com/auth/gmail.compose']
        )
        
        delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
        service = build('gmail', 'v1', credentials=delegated_credentials)
        
        service.users().drafts().delete(
            userId=params["values"]["userId"],
            id=params["values"]["draftId"]
        ).execute()
        
        return JsonArtifact({
            'success': True,
            'draftId': params["values"]["draftId"]
        })

def init_tool() -> BaseTool:
    return GmailTool()