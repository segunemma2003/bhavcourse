# Apple Authentication with Firebase Setup Guide

This guide explains how to set up and use Apple authentication with Firebase in your Django API.

## Overview

The implementation provides an API endpoint for authenticating users using Apple Sign-In with Firebase. The authentication flow works as follows:

1. User signs in with Apple on the client side
2. Client gets Firebase ID token from Apple authentication
3. Client sends ID token to Django API
4. API verifies token with Firebase and creates/updates user account
5. API returns Django authentication token

## API Endpoint

### POST `/api/auth/firebase-apple/`

Authenticates a user using Firebase ID token from Apple Authentication.

#### Request Body

```json
{
  "id_token": "firebase_id_token_from_apple_auth",
  "nonce": "optional_nonce_value"
}
```

#### Response

**Success (200 OK):**

```json
{
  "key": "django_auth_token",
  "user": {
    "id": 123,
    "email": "user@example.com",
    "full_name": "John Doe",
    "phone_number": "+1234567890",
    "auth_provider": "apple",
    "is_new_user": false
  },
  "message": "Apple authentication successful"
}
```

**Error (400 Bad Request):**

```json
{
  "id_token": ["This field is required."]
}
```

**Error (401 Unauthorized):**

```json
{
  "error": "Firebase Apple authentication failed: Invalid ID token"
}
```

## Firebase Configuration

### 1. Enable Apple Authentication in Firebase Console

1. Go to Firebase Console → Authentication → Sign-in method
2. Enable Apple provider
3. Configure your Apple Developer account settings:
   - Service ID
   - Team ID
   - Key ID
   - Private Key

### 2. Firebase Configuration in Django

Ensure your Firebase credentials are properly configured in `settings.py`:

```python
FIREBASE_CREDENTIALS_PATH = os.path.join(BASE_DIR, 'firebase-credentials.json')
```

### 3. Required Dependencies

Make sure you have the Firebase Admin SDK installed:

```bash
pip install firebase-admin
```

## Client-Side Implementation

### iOS (Swift)

```swift
import AuthenticationServices
import FirebaseAuth

class AppleSignInManager: NSObject, ASAuthorizationControllerDelegate {

    func signInWithApple() {
        let request = ASAuthorizationAppleIDProvider().createRequest()
        request.requestedScopes = [.fullName, .email]

        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.performRequests()
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        if let appleIDCredential = authorization.credential as? ASAuthorizationAppleIDCredential {
            guard let appleIDToken = appleIDCredential.identityToken else { return }

            let idTokenString = String(data: appleIDToken, encoding: .utf8)!

            // Create Firebase credential
            let credential = OAuthProvider.credential(
                withProviderID: "apple.com",
                idToken: idTokenString,
                rawNonce: nonce
            )

            // Sign in with Firebase
            Auth.auth().signIn(with: credential) { (result, error) in
                if let error = error {
                    print("Firebase sign in error: \(error)")
                    return
                }

                // Get Firebase ID token
                result?.user.getIDToken { (idToken, error) in
                    if let error = error {
                        print("Error getting ID token: \(error)")
                        return
                    }

                    // Send to Django API
                    self.sendToDjangoAPI(idToken: idToken!)
                }
            }
        }
    }

    func sendToDjangoAPI(idToken: String) {
        let url = URL(string: "https://your-api.com/api/auth/firebase-apple/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = ["id_token": idToken]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request) { data, response, error in
            // Handle response
            if let data = data {
                let response = try? JSONSerialization.jsonObject(with: data)
                print("Django API response: \(response)")
            }
        }.resume()
    }
}
```

### Android (Kotlin)

```kotlin
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.OAuthProvider

class AppleSignInManager {

    fun signInWithApple() {
        val provider = OAuthProvider.newBuilder("apple.com")

        FirebaseAuth.getInstance().pendingAuthResult?.let { result ->
            result.addOnSuccessListener { authResult ->
                // Handle successful sign-in
                authResult.user?.getIdToken(false)?.addOnSuccessListener { token ->
                    sendToDjangoAPI(token)
                }
            }
        } ?: FirebaseAuth.getInstance().startActivityForSignInWithProvider(
            activity,
            provider.build()
        ).addOnSuccessListener { authResult ->
            authResult.user?.getIdToken(false)?.addOnSuccessListener { token ->
                sendToDjangoAPI(token)
            }
        }
    }

    private fun sendToDjangoAPI(idToken: String) {
        val url = URL("https://your-api.com/api/auth/firebase-apple/")
        val connection = url.openConnection() as HttpURLConnection

        connection.requestMethod = "POST"
        connection.setRequestProperty("Content-Type", "application/json")
        connection.doOutput = true

        val body = JSONObject().apply {
            put("id_token", idToken)
        }

        connection.outputStream.use { os ->
            os.write(body.toString().toByteArray())
        }

        val response = connection.inputStream.bufferedReader().use { it.readText() }
        println("Django API response: $response")
    }
}
```

### Web (JavaScript)

```javascript
import { initializeApp } from "firebase/app";
import { getAuth, signInWithPopup, OAuthProvider } from "firebase/auth";

const firebaseConfig = {
  // Your Firebase config
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

async function signInWithApple() {
  const provider = new OAuthProvider("apple.com");

  try {
    const result = await signInWithPopup(auth, provider);
    const idToken = await result.user.getIdToken();

    // Send to Django API
    await sendToDjangoAPI(idToken);
  } catch (error) {
    console.error("Apple sign in error:", error);
  }
}

async function sendToDjangoAPI(idToken) {
  try {
    const response = await fetch(
      "https://your-api.com/api/auth/firebase-apple/",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          id_token: idToken,
        }),
      }
    );

    const data = await response.json();
    console.log("Django API response:", data);

    if (response.ok) {
      // Store the Django token
      localStorage.setItem("django_token", data.key);
    }
  } catch (error) {
    console.error("Error sending to Django API:", error);
  }
}
```

## Security Considerations

### 1. Token Verification

The API verifies the Firebase ID token server-side using Firebase Admin SDK, ensuring the token is valid and not tampered with.

### 2. Nonce Validation

For additional security, you can implement nonce validation:

```python
# In your view
if nonce:
    # Validate nonce against stored value
    if not validate_nonce(nonce):
        return Response(
            {'error': 'Invalid nonce'},
            status=status.HTTP_400_BAD_REQUEST
        )
```

### 3. Rate Limiting

Consider implementing rate limiting on the authentication endpoint to prevent abuse.

### 4. HTTPS

Always use HTTPS in production to secure token transmission.

## Error Handling

The API handles various error scenarios:

- **Invalid ID token**: Returns 401 Unauthorized
- **Missing required fields**: Returns 400 Bad Request
- **Firebase errors**: Returns appropriate error messages
- **User creation errors**: Logs errors and returns 500 Internal Server Error

## User Management

### User Creation

- New users are automatically created when they first authenticate
- User email is extracted from the Firebase token
- If email is not available (Apple privacy feature), a placeholder email is created using the UID

### User Updates

- Existing users' profiles are updated with new information from Apple
- Full name is updated if provided and not already set

### User Identification

- Users are primarily identified by email
- For users without email, UID-based placeholder emails are used
- This ensures consistent user identification across sessions

## Testing

### Test the API Endpoint

```bash
curl -X POST https://your-api.com/api/auth/firebase-apple/ \
  -H "Content-Type: application/json" \
  -d '{
    "id_token": "your_firebase_id_token"
  }'
```

### Test with Invalid Token

```bash
curl -X POST https://your-api.com/api/auth/firebase-apple/ \
  -H "Content-Type: application/json" \
  -d '{
    "id_token": "invalid_token"
  }'
```

## Troubleshooting

### Common Issues

1. **Firebase not initialized**: Ensure Firebase credentials are properly configured
2. **Invalid token**: Verify the token is from Apple authentication
3. **Missing email**: Handle cases where Apple doesn't provide email
4. **User creation fails**: Check database permissions and constraints

### Debug Logging

The implementation includes comprehensive logging. Check your Django logs for:

- Firebase initialization status
- Token verification results
- User creation/update operations
- Error details

## Additional Features

### Custom User Fields

You can extend the user data returned by modifying the `user_data` dictionary in the view:

```python
user_data = {
    'id': user.id,
    'email': user.email,
    'full_name': user.full_name,
    'phone_number': user.phone_number,
    'auth_provider': 'apple',
    'is_new_user': created,
    'date_joined': user.date_joined.isoformat(),
    'profile_picture': user.get_profile_picture_url(),
}
```

### Session Management

The API returns a Django authentication token that can be used for subsequent requests:

```python
headers = {
    'Authorization': f'Token {django_token}',
    'Content-Type': 'application/json'
}
```

This completes the Apple authentication setup with Firebase in your Django API!
