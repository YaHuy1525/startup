#!/usr/bin/env python3
"""
Simple YouTube refresh token generator using http://localhost redirect.
"""

import json
import urllib.request
from urllib.parse import urlencode

def generate_refresh_token():
    # Your credentials
    CLIENT_ID = "923431671500-j7s03dll8j1s5ad4t6s4d3i62i5oplsi.apps.googleusercontent.com"
    CLIENT_SECRET = "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"
    REDIRECT_URI = "http://localhost"  # Try this simpler URI
    SCOPE = "https://www.googleapis.com/auth/youtube.upload"
    
    print("🔑 YouTube Refresh Token Generator")
    print("=" * 50)
    print(f"Client ID: {CLIENT_ID}")
    print(f"Redirect URI: {REDIRECT_URI}")
    print(f"Scope: {SCOPE}")
    print()
    
    # Build authorization URL with forced consent
    auth_params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE,
        'response_type': 'code',
        'access_type': 'offline',  # Required for refresh token
        'prompt': 'consent',       # Forces consent screen
        'state': 'random_state_string'
    }
    
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(auth_params)}"
    
    print("🌐 STEP 1: Visit this URL in your browser:")
    print(auth_url)
    print()
    print("📋 STEP 2: After authorization, you'll be redirected to:")
    print(f"{REDIRECT_URI}/?code=AUTHORIZATION_CODE&state=random_state_string")
    print()
    print("🔍 STEP 3: Copy the entire URL from your browser address bar")
    print()
    
    # Get the full redirect URL from user
    redirect_url = input("📝 Paste the full redirect URL here: ").strip()
    
    if not redirect_url:
        print("❌ No redirect URL provided!")
        return None
    
    # Extract authorization code from the URL
    if 'code=' in redirect_url:
        auth_code = redirect_url.split('code=')[1].split('&')[0]
        print(f"✅ Extracted authorization code: {auth_code[:20]}...")
    else:
        print("❌ No authorization code found in the URL!")
        return None
    
    # Exchange authorization code for tokens
    token_data = {
        'code': auth_code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    print("🔄 STEP 4: Exchanging authorization code for tokens...")
    
    try:
        token_request = urllib.request.Request(
            'https://oauth2.googleapis.com/token',
            data=urlencode(token_data).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        with urllib.request.urlopen(token_request) as response:
            token_response = json.loads(response.read().decode())
            
        if 'refresh_token' in token_response:
            refresh_token = token_response['refresh_token']
            access_token = token_response.get('access_token')
            
            print("🎉 SUCCESS! New tokens generated:")
            print("=" * 50)
            print(f"🔑 Refresh Token: {refresh_token}")
            print(f"🎫 Access Token: {access_token[:50]}...")
            print()
            print("📝 Add this to your .env file:")
            print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")
            print()
            print("💡 Your refresh token will work with the updated client credentials!")
            
            return refresh_token
        else:
            print("❌ No refresh token received!")
            print("Response:", token_response)
            return None
            
    except Exception as e:
        print(f"❌ Error exchanging code for tokens: {e}")
        return None

if __name__ == "__main__":
    print("⚠️  Make sure your Google Cloud Console has this redirect URI:")
    print("http://localhost")
    print()
    
    refresh_token = generate_refresh_token()
    if refresh_token:
        print("\n✅ Refresh token generation completed successfully!")
    else:
        print("\n❌ Refresh token generation failed!")
