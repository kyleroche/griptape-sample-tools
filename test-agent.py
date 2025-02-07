from griptape.structures import Agent
from google_docs.tool import GoogleDocsTool
from google_oauth.tool import GoogleOAuthTool

prompts = [
    "create me a sample resume in google docs",
    "create notes for a fake meeting using template: 15Z8AVKf6c8pOjmisXxoz8Q3df6jXMwlvx7NG-PTT7wE. the meeting was about a project review for secret project. i met with the bobs. make up content for the meeting notes. PRINT THE NEW DOCUMENT TO THE CONSOLE",
    "what meetings do I have today?",
    "Create a calendar event for feb 3, 2025 at 5pm pacific with Ryan (ryan@griptape.ai) with a subject of Project Review. add a zoom meeting",
    "List my unread emails from the last 24 hours",
    "Create a draft email to kyro@griptape.ai with subject 'i have had enough' and body 'we ship nodes or i am out'",
    "Create a new google doc titled 'Project Notes' with description 'Meeting notes from project review'",
    "Start the OAuth process to authenticate with Google",  # Will return URL for auth
    "Test my Google OAuth credentials with code: 4/0ASVgi3K49CKHGqnjo7vbqUpx83Rj9iDKO2euja2GqzcSViSEcWCtZka1vT-MGkWzvrJugg"  # Will test API access
]

if __name__ == "__main__":
    agent = Agent(tools=[GoogleDocsTool(), GoogleOAuthTool()])
    # Run the second prompt (index 1) from the prompts list
    response = agent.run(prompts[1])
    print(response)