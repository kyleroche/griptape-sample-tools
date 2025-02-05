from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from griptape.artifacts import TextArtifact, BaseArtifact
from griptape.tools import BaseTool
from griptape.utils.decorators import activity
from griptape.drivers import GriptapeCloudFileManagerDriver
from schema import Schema, Literal, Optional
import os.path
import pickle
import traceback
import base64
import json
import tempfile
from urllib.parse import quote  # Add this import at the top

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/docs',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.modify'
]

class GoogleOAuthTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.use_cloud = os.getenv('GRIPTAPE_CLOUD_GOOGLE_OAUTH', '').lower() == 'true'
        self.headless = os.getenv('GRIPTAPE_CLOUD_GOOGLE_OAUTH_HEADLESS', '').lower() == 'true'
        self.redirect_uri = os.getenv('GRIPTAPE_CLOUD_GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost')
        if self.use_cloud:
            self.cloud_driver = GriptapeCloudFileManagerDriver(
                api_key=os.getenv('GRIPTAPE_CLOUD_API_KEY'),
                bucket_id=os.getenv('GRIPTAPE_CLOUD_GOOGLE_OAUTH_BUCKET_ID')
            )

    def _get_credentials_json(self):
        """Get credentials.json either from local file or Griptape Cloud"""
        if not self.use_cloud:
            if not os.path.exists('credentials.json'):
                return None
            with open('credentials.json', 'r') as f:
                return f.read()
        
        try:
            return self.cloud_driver.load_file('credentials.json')
        except Exception as e:
            print(f"Error loading credentials from Griptape Cloud: {str(e)}")
            traceback.print_exc()
            return None

    @activity(
        config={
            "description": "Handles OAuth authentication flow",
            "schema": Schema({
                Literal(
                    "action",
                    description="Action to perform - 'start' to begin OAuth, 'code' to complete OAuth with authorization code, or 'test' to verify credentials"
                ): str,
                Optional(Literal(
                    "authorization_code",
                    description="The authorization code received from OAuth redirect"
                )): str
            })
        }
    )
    def authenticate(self, params: dict) -> BaseArtifact:
        """Handles OAuth authentication flow"""
        try:
            action = params["values"]["action"].lower()
            
            if action == "start":
                if self.use_cloud:
                    try:
                        # Get credentials from cloud
                        creds_content = self.cloud_driver.load_file('credentials.json')
                        
                        # Write to temp file for OAuth flow
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp:
                            temp.write(creds_content.value.decode('utf-8'))
                            temp_path = temp.name
                        
                        try:
                            flow = InstalledAppFlow.from_client_secrets_file(temp_path, SCOPES)
                            
                            if self.headless:
                                # Headless mode - return URL for manual auth
                                flow.redirect_uri = self.redirect_uri
                                auth_url, _ = flow.authorization_url(
                                    access_type='offline',
                                    include_granted_scopes='true'
                                )
                                
                                print("\nDEBUG - Auth URL:")
                                print("Type:", type(auth_url))
                                print("Raw URL:", repr(auth_url))
                                print("URL components:", auth_url.split('?'))
                                print()
                                
                                return TextArtifact(
                                    "🔐 Please complete OAuth flow:\n\n"
                                    f"URL: {auth_url}\n\n"
                                    "Instructions:\n"
                                    "1. Visit the URL above\n"
                                    "2. Complete the authentication process\n"
                                    "3. Copy the authorization code\n"
                                    "4. Use the code in your next request with action='code'"
                                )
                            else:
                                # Browser mode - launch local server
                                creds = flow.run_local_server(port=0)
                                gmail_service = build('gmail', 'v1', credentials=creds)
                                profile = gmail_service.users().getProfile(userId='me').execute()
                                user_email = profile.get('emailAddress')
                                return TextArtifact(f"✅ Authentication successful for {user_email}! (Cloud mode: token not saved)")
                        finally:
                            os.unlink(temp_path)
                            
                    except Exception as e:
                        traceback.print_exc()
                        return TextArtifact(
                            "Error: Failed to load credentials.json from Griptape Cloud!\n"
                            f"Error details: {str(e)}"
                        )
                else:
                    # Local mode - check local file
                    if not os.path.exists('credentials.json'):
                        return TextArtifact(
                            "Error: credentials.json not found in local file system!\n"
                            "Please ensure credentials.json exists and is accessible.\n"
                            "To get credentials:\n"
                            "1. Go to https://console.cloud.google.com\n"
                            "2. Select your project\n"
                            "3. Go to APIs & Services > Credentials\n"
                            "4. Create OAuth 2.0 Client ID (Desktop application)\n"
                            "5. Download and save as credentials.json"
                        )
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                    
                    # Get user email
                    gmail_service = build('gmail', 'v1', credentials=creds)
                    profile = gmail_service.users().getProfile(userId='me').execute()
                    user_email = profile.get('emailAddress')
                    
                    # Save token locally
                    email_prefix = user_email.split('@')[0]
                    token_file = f"{email_prefix}.pickle"
                    with open(token_file, 'wb') as token:
                        pickle.dump(creds, token)
                    return TextArtifact(f"✅ Authentication successful! Credentials saved as {token_file}")
                
            elif action == "code":
                if not "authorization_code" in params["values"]:
                    return TextArtifact("Error: authorization_code is required for this action")
                
                try:
                    # Get credentials from cloud and complete OAuth
                    creds_content = self.cloud_driver.load_file('credentials.json')
                    
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp:
                        temp.write(creds_content.value.decode('utf-8'))
                        temp_path = temp.name
                    
                    try:
                        flow = InstalledAppFlow.from_client_secrets_file(temp_path, SCOPES)
                        flow.redirect_uri = self.redirect_uri
                        flow.fetch_token(code=params["values"]["authorization_code"])
                        creds = flow.credentials
                        
                        # Get user email
                        gmail_service = build('gmail', 'v1', credentials=creds)
                        profile = gmail_service.users().getProfile(userId='me').execute()
                        user_email = profile.get('emailAddress')
                        
                        return TextArtifact(f"✅ Authentication successful for {user_email}! (Cloud mode: token not saved)")
                    finally:
                        os.unlink(temp_path)
                    
                except Exception as e:
                    traceback.print_exc()
                    return TextArtifact(f"Error completing OAuth flow: {str(e)}")
            
            elif action == "test":
                if self.use_cloud:
                    return TextArtifact("Test action not available in cloud mode. Please authenticate again if needed.")
                
                creds = self._get_credentials()
                if not creds:
                    return TextArtifact("No valid credentials found. Please run authenticate with action='start' first.")
                
                result = self._test_apis(creds)
                return TextArtifact(result)
            
            else:
                return TextArtifact(f"Invalid action: {action}. Use 'start' or 'test'")
            
        except Exception as e:
            print(f"Error in OAuth flow: {str(e)}")
            traceback.print_exc()
            raise

    def _get_credentials(self):
        """Helper to get/refresh credentials"""
        # Look for any .pickle files
        pickle_files = [f for f in os.listdir('.') if f.endswith('.pickle')]
        
        for pickle_file in pickle_files:
            try:
                with open(pickle_file, 'rb') as token:
                    creds = pickle.load(token)
                
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                        # Save refreshed credentials back to same file
                        with open(pickle_file, 'wb') as token:
                            pickle.dump(creds, token)
                        return creds
                else:
                    return creds
            except Exception as e:
                print(f"Error with {pickle_file}: {str(e)}")
                continue
        
        return None

    def _test_apis(self, creds):
        """Tests API access with current credentials"""
        results = []
        try:
            # Test Docs API
            docs_service = build('docs', 'v1', credentials=creds)
            doc = docs_service.documents().create(body={'title': 'OAuth Test Document'}).execute()
            results.append(f"✅ Docs API: Created test document: {doc.get('title')}")
            
            # Test Calendar API
            calendar_service = build('calendar', 'v3', credentials=creds)
            calendar_list = calendar_service.calendarList().list().execute()
            results.append(f"✅ Calendar API: Listed {len(calendar_list.get('items', []))} calendars")
            
            # Test Gmail API
            gmail_service = build('gmail', 'v1', credentials=creds)
            profile = gmail_service.users().getProfile(userId='me').execute()
            results.append(f"✅ Gmail API: Connected to {profile.get('emailAddress')}")
            
            results.append("\n✨ All API tests passed successfully!")
        except Exception as e:
            results.append(f"❌ Error testing APIs: {str(e)}")
        
        return "\n".join(results)

def init_tool() -> BaseTool:
    return GoogleOAuthTool() 