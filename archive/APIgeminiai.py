from google import genai

client = genai.Client(
    vertexai=True,
    project="YOUR_GCP_PROJECT_NUMBER",
    location="us-central1"
)

response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="Explain how AI works in a few words"
)

print(response.text)