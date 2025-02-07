from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import Dict
import os
from schema import Schema, Literal, Optional, Or
from griptape.artifacts import JsonArtifact
from griptape.tools import BaseTool
from griptape.utils.decorators import activity
import traceback
import json

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
            "description": "Reads a Google Doc template and returns its structure",
            "schema": Schema({
                Literal(
                    "template_id",
                    description="ID of the template document to read"
                ): str
            })
        }
    )
    def read_template(self, params: dict) -> JsonArtifact:
        """Reads a template doc and returns its structure."""
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
                scopes=[
                    'https://www.googleapis.com/auth/drive',        # Full Drive access
                    'https://www.googleapis.com/auth/drive.file',   # For creating/editing docs
                    'https://www.googleapis.com/auth/docs'          # For docs API
                ]
            )
            
            delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
            docs_service = build('docs', 'v1', credentials=delegated_credentials)
            
            template_id = params["values"]["template_id"]
            
            # Read the template content
            template_doc = docs_service.documents().get(
                documentId=template_id
            ).execute()
            
            # Extract structure (paragraphs, styles, etc)
            structure = []
            for element in template_doc.get('body').get('content', []):
                if 'paragraph' in element:
                    para = element.get('paragraph')
                    para_structure = {
                        'style': para.get('paragraphStyle', {}),
                        'bullet': para.get('bullet', {}),  # Capture bullet/list formatting
                        'elements': []
                    }
                    
                    for item in para.get('elements', []):
                        if 'textRun' in item:
                            text_run = item.get('textRun', {})
                            para_structure['elements'].append({
                                'text': text_run.get('content', ''),
                                'style': text_run.get('textStyle', {}),
                                'type': 'textRun'
                            })
                        elif 'inlineObjectElement' in item:
                            # Handle inline objects (images, etc)
                            para_structure['elements'].append({
                                'type': 'inlineObject',
                                'data': item.get('inlineObjectElement', {})
                            })
                    
                    structure.append(para_structure)
            
            # Extract structure and convert to JSON string
            template_data = {
                'template_id': template_id,
                'title': template_doc.get('title'),
                'structure': structure
            }
            
            return JsonArtifact(json.dumps(template_data))  # Return stringified JSON
            
        except Exception as e:
            print(f"Error reading template: {str(e)}")
            traceback.print_exc()
            raise

    @activity(
        config={
            "description": "Creates a Google Doc from a complete JSON structure including all formatting",
            "schema": Schema({
                Literal(
                    "title",
                    description="Title of the new document"
                ): str,
                Literal(
                    "content",
                    description="Complete Google Doc JSON structure with formatting"
                ): dict
            })
        }
    )
    def create_doc_from_json(self, params: dict) -> JsonArtifact:
        """Creates a new doc from complete JSON structure."""
        try:
            # Get credentials and service
            credentials = service_account.Credentials.from_service_account_info(
                SERVICE_ACCOUNT_INFO,
                scopes=['https://www.googleapis.com/auth/documents']
            )
            docs_service = build('docs', 'v1', credentials=credentials)
            
            # Create new empty doc
            doc = docs_service.documents().create(body={'title': params["values"]["title"]}).execute()
            doc_id = doc.get('documentId')
            
            # Build requests from JSON structure
            requests = []
            current_index = 1
            
            content = params["values"]["content"]
            
            # Convert the content structure to Google Docs API requests
            for item in content.get('structure', []):
                # Add paragraph style
                if item.get('style'):
                    requests.append({
                        'updateParagraphStyle': {
                            'range': {
                                'startIndex': current_index,
                                'endIndex': current_index + 1
                            },
                            'paragraphStyle': item['style'],
                            'fields': '*'  # Update all fields
                        }
                    })
                
                # Add elements (text runs, inline objects, etc)
                for element in item.get('elements', []):
                    if element['type'] == 'textRun':
                        text = element['text']
                        # Insert text
                        requests.append({
                            'insertText': {
                                'location': {'index': current_index},
                                'text': text
                            }
                        })
                        
                        # Apply text style
                        if element.get('style'):
                            requests.append({
                                'updateTextStyle': {
                                    'range': {
                                        'startIndex': current_index,
                                        'endIndex': current_index + len(text)
                                    },
                                    'textStyle': element['style'],
                                    'fields': '*'  # Update all style fields
                                }
                            })
                        current_index += len(text)
                    
                    elif element['type'] == 'inlineObject':
                        # Handle inline objects if needed
                        pass
                
                # Add newline after paragraph
                requests.append({
                    'insertText': {
                        'location': {'index': current_index},
                        'text': '\n'
                    }
                })
                current_index += 1
            
            # Apply all updates
            if requests:
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': requests}
                ).execute()
            
            return JsonArtifact({
                'documentId': doc_id,
                'title': params["values"]["title"],
                'url': f"https://docs.google.com/document/d/{doc_id}/edit"
            })
            
        except Exception as e:
            print(f"Error creating doc: {str(e)}")
            traceback.print_exc()
            raise


def init_tool() -> BaseTool:
    return GoogleDocsTool() 