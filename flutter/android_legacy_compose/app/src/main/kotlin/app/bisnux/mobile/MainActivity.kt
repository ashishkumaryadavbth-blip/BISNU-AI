package app.bisnux.mobile

import android.content.Context
import android.os.Bundle
import android.util.Base64
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.security.SecureRandom
import java.util.UUID
import javax.net.ssl.HttpsURLConnection
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

private const val BACKEND_URL = "http://10.0.2.2:8000"

class MainActivity : ComponentActivity() {

    private lateinit var credentialManager: CredentialManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        credentialManager = CredentialManager.create(this)

        setContent {
            BISNUXApp(
                credentialManager = credentialManager,
                activity = this
            )
        }
    }
}

@Composable
fun BISNUXApp(
    credentialManager: CredentialManager,
    activity: MainActivity
) {
    val scope = rememberCoroutineScope()

    var loggedIn by remember {
        mutableStateOf(
            SessionStore(activity).isLoggedIn()
        )
    }

    var loading by remember {
        mutableStateOf(false)
    }

    var error by remember {
        mutableStateOf<String?>(null)
    }

    MaterialTheme {
        Surface(
            modifier = Modifier.fillMaxSize()
        ) {

            if (!loggedIn) {

                LoginScreen(
                    loading = loading,
                    error = error,
                    onGoogleLogin = {

                        scope.launch {

                            loading = true
                            error = null

                            try {

                                val token = googleSignIn(
                                    activity = activity,
                                    credentialManager = credentialManager
                                )

                                val result = sendTokenToBackend(token)

                                if (result.success) {

                                    SessionStore(activity).save(
                                        sessionToken = result.sessionToken,
                                        userId = result.userId,
                                        name = result.name,
                                        email = result.email
                                    )

                                    loggedIn = true

                                } else {
                                    error = "Google login failed."
                                }

                            } catch (e: Exception) {

                                error =
                                    e.message
                                        ?: "Google login failed."

                            } finally {
                                loading = false
                            }
                        }
                    }
                )

            } else {

                ChatScreen(
                    name = SessionStore(activity).getName(),
                    onLogout = {

                        SessionStore(activity).clear()
                        loggedIn = false
                    }
                )
            }
        }
    }
}

@Composable
fun LoginScreen(
    loading: Boolean,
    error: String?,
    onGoogleLogin: () -> Unit
) {

    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        contentAlignment = Alignment.Center
    ) {

        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {

            Text(
                text = "BISNU-X",
                style = MaterialTheme.typography.displaySmall
            )

            Spacer(
                modifier = Modifier.height(12.dp)
            )

            Text(
                text = "Independent AI Platform",
                style = MaterialTheme.typography.bodyLarge
            )

            Spacer(
                modifier = Modifier.height(40.dp)
            )

            Button(
                modifier = Modifier.fillMaxWidth(),
                enabled = !loading,
                onClick = onGoogleLogin,
                shape = RoundedCornerShape(16.dp)
            ) {

                if (loading) {

                    CircularProgressIndicator(
                        modifier = Modifier.height(20.dp),
                        strokeWidth = 2.dp
                    )

                } else {

                    Text("Continue with Google")
                }
            }

            if (error != null) {

                Spacer(
                    modifier = Modifier.height(20.dp)
                )

                Text(
                    text = error,
                    color = MaterialTheme.colorScheme.error
                )
            }
        }
    }
}

@Composable
fun ChatScreen(
    name: String,
    onLogout: () -> Unit
) {

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp)
    ) {

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {

            Column {

                Text(
                    text = "BISNU-X",
                    style = MaterialTheme.typography.headlineMedium
                )

                Text(
                    text = "Hello, $name"
                )
            }

            OutlinedButton(
                onClick = onLogout
            ) {
                Text("Logout")
            }
        }

        Spacer(
            modifier = Modifier.height(40.dp)
        )

        Text(
            text = "Chat is ready.",
            style = MaterialTheme.typography.titleLarge
        )

        Spacer(
            modifier = Modifier.height(8.dp)
        )

        Text(
            text = "AI backend connection will use the existing BISNU-X /v1/chat API."
        )
    }
}

private fun generateNonce(): String {

    val bytes = ByteArray(32)

    SecureRandom().nextBytes(bytes)

    return Base64.encodeToString(
        bytes,
        Base64.NO_WRAP or
                Base64.URL_SAFE or
                Base64.NO_PADDING
    )
}

private suspend fun googleSignIn(
    activity: MainActivity,
    credentialManager: CredentialManager
): String {

    val webClientId =
        activity.getString(
            R.string.google_web_client_id
        )

    val option =
        GetSignInWithGoogleOption.Builder(
            webClientId
        )
            .setNonce(generateNonce())
            .build()

    val request =
        GetCredentialRequest.Builder()
            .addCredentialOption(option)
            .build()

    val result =
        credentialManager.getCredential(
            activity,
            request
        )

    val credential = result.credential

    if (
        credential is CustomCredential &&
        credential.type ==
        GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
    ) {

        val googleCredential =
            GoogleIdTokenCredential.createFrom(
                credential.data
            )

        return googleCredential.idToken
    }

    throw IllegalStateException(
        "Google ID token was not returned."
    )
}

data class BackendLoginResult(
    val success: Boolean,
    val sessionToken: String,
    val userId: String,
    val name: String,
    val email: String
)

private suspend fun sendTokenToBackend(
    idToken: String
): BackendLoginResult =
    withContext(Dispatchers.IO) {

        val url =
            URL("$BACKEND_URL/v1/auth/google")

        val connection =
            url.openConnection() as HttpURLConnection

        try {

            connection.requestMethod = "POST"
            connection.setRequestProperty(
                "Content-Type",
                "application/json"
            )

            connection.connectTimeout = 15000
            connection.readTimeout = 30000
            connection.doOutput = true

            val body =
                JSONObject()
                    .put("id_token", idToken)
                    .toString()

            connection.outputStream.use { output ->
                output.write(
                    body.toByteArray(
                        Charsets.UTF_8
                    )
                )
            }

            val status =
                connection.responseCode

            val stream =
                if (status in 200..299) {
                    connection.inputStream
                } else {
                    connection.errorStream
                }

            val response =
                stream
                    ?.bufferedReader()
                    ?.use { it.readText() }
                    ?: ""

            if (status !in 200..299) {

                throw IllegalStateException(
                    "Backend error $status: $response"
                )
            }

            val json =
                JSONObject(response)

            BackendLoginResult(
                success =
                    json.optBoolean(
                        "success",
                        false
                    ),

                sessionToken =
                    json.optString(
                        "session_token"
                    ),

                userId =
                    json.optString(
                        "user_id"
                    ),

                name =
                    json.optString(
                        "name"
                    ),

                email =
                    json.optString(
                        "email"
                    )
            )

        } finally {

            connection.disconnect()
        }
    }

class SessionStore(
    private val context: Context
) {

    private val preferences =
        context.getSharedPreferences(
            "bisnu_x_session",
            Context.MODE_PRIVATE
        )

    fun save(
        sessionToken: String,
        userId: String,
        name: String,
        email: String
    ) {

        preferences.edit()
            .putString(
                "session_token",
                sessionToken
            )
            .putString(
                "user_id",
                userId
            )
            .putString(
                "name",
                name
            )
            .putString(
                "email",
                email
            )
            .apply()
    }

    fun isLoggedIn(): Boolean =
        !preferences
            .getString(
                "session_token",
                null
            )
            .isNullOrBlank()

    fun getName(): String =
        preferences.getString(
            "name",
            "User"
        ) ?: "User"

    fun getToken(): String? =
        preferences.getString(
            "session_token",
            null
        )

    fun clear() {

        preferences.edit()
            .clear()
            .apply()
    }
}