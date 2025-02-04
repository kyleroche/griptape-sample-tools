from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import Dict
import os
from schema import Schema, Literal, Optional
from griptape.artifacts import JsonArtifact
from griptape.tools import BaseTool
from griptape.utils.decorators import activity
import traceback

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
    #"client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('GOOGLE_CLIENT_EMAIL').replace('@', '%40')}"
}

class GoogleDocsTool(BaseTool):
    def __init__(self):
        super().__init__()

    @activity(
        config={
            "description": "Creates a new blank Google Doc",
            "schema": Schema({
                Literal(
                    "title",
                    description="Title of the document"
                ): str,
                Optional(Literal(
                    "description",
                    description="Description of the document"
                )): str
            })
        }
    )
    def create_doc(self, params: dict) -> JsonArtifact:
        """Creates a new Google Doc and returns its metadata."""
        try:
            # Get the private key and clean it up
            private_key = os.getenv('GOOGLE_PRIVATE_KEY')
            if private_key and "\\n" in private_key:
                private_key = private_key.replace("\\n", "\n")
            
            service_account_info = {
                "type": "service_account",
                "project_id": os.getenv('GOOGLE_PROJECT_ID'),
                "private_key_id": os.getenv('GOOGLE_PRIVATE_KEY_ID'),
                "private_key": private_key,
                "client_email": os.getenv('GOOGLE_CLIENT_EMAIL'),
                "client_id": os.getenv('GOOGLE_CLIENT_ID'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            }
            
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/docs']
            )
            
            delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
            docs_service = build('docs', 'v1', credentials=delegated_credentials)

            # Create an empty doc
            doc = docs_service.documents().create(body={'title': params["values"]["title"]}).execute()

            # If description provided, add it to the document
            if params["values"].get("description"):
                requests = [
                    {
                        'insertText': {
                            'location': {
                                'index': 1,
                            },
                            'text': f"{params['values']['description']}\n\n"
                        }
                    }
                ]
                docs_service.documents().batchUpdate(
                    documentId=doc.get('documentId'),
                    body={'requests': requests}
                ).execute()

            return JsonArtifact({
                'documentId': doc.get('documentId'),
                'title': doc.get('title'),
                'url': f"https://docs.google.com/document/d/{doc.get('documentId')}/edit"
            })
        except Exception as e:
            print(f"Error creating doc: {str(e)}")
            traceback.print_exc()
            raise

def init_tool() -> BaseTool:
    return GoogleDocsTool() 