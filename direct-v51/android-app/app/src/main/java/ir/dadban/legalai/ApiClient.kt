package ir.dadban.legalai

import android.content.ContentResolver
import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.BufferedSink
import org.json.JSONObject
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

class ApiException(val statusCode: Int, message: String) : IOException(message)

class ApiClient(private val context: Context, private val tokenStore: SecureTokenStore) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(240, TimeUnit.SECONDS)
        .writeTimeout(240, TimeUnit.SECONDS)
        .build()
    private val base = BuildConfig.API_BASE_URL.trimEnd('/')

    private fun request(path: String): Request.Builder {
        val builder = Request.Builder().url(base + path).header("Accept", "application/json")
        tokenStore.load()?.let { builder.header("Authorization", "Bearer $it") }
        return builder
    }

    private fun executeJson(request: Request): JSONObject {
        client.newCall(request).execute().use { response ->
            val text = response.body?.string().orEmpty()
            val json = runCatching { JSONObject(text) }.getOrElse { JSONObject() }
            if (!response.isSuccessful) {
                val detail = json.optString("detail").ifBlank { "خطای ارتباط با سرور (${response.code})" }
                throw ApiException(response.code, detail)
            }
            return json
        }
    }

    private fun jsonBody(json: JSONObject): RequestBody =
        json.toString().toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())

    suspend fun phoneLogin(phone: String): JSONObject = withContext(Dispatchers.IO) {
        executeJson(request("/api/mobile/auth/phone-login").post(jsonBody(JSONObject().put("phone", phone))).build())
    }

    suspend fun requestOtp(phone: String): JSONObject = withContext(Dispatchers.IO) {
        executeJson(request("/api/mobile/auth/request-otp").post(jsonBody(JSONObject().put("phone", phone))).build())
    }

    suspend fun verifyOtp(challengeId: String, code: String): JSONObject = withContext(Dispatchers.IO) {
        executeJson(request("/api/mobile/auth/verify").post(jsonBody(JSONObject().put("challenge_id", challengeId).put("code", code))).build())
    }

    suspend fun me(): JSONObject = withContext(Dispatchers.IO) { executeJson(request("/api/mobile/auth/me").get().build()) }

    suspend fun saveProfile(fullName: String, province: String, city: String): JSONObject = withContext(Dispatchers.IO) {
        executeJson(
            request("/api/mobile/profile").put(
                jsonBody(JSONObject().put("full_name", fullName).put("province", province).put("city", city))
            ).build()
        )
    }

    suspend fun logout(): JSONObject = withContext(Dispatchers.IO) {
        executeJson(request("/api/mobile/auth/logout").post(ByteArray(0).toRequestBody()).build())
    }

    suspend fun checkout(): JSONObject = withContext(Dispatchers.IO) {
        executeJson(request("/api/mobile/billing/checkout").post(jsonBody(JSONObject().put("plan_code", "premium_monthly"))).build())
    }

    suspend fun paymentStatus(paymentId: String): JSONObject = withContext(Dispatchers.IO) {
        executeJson(request("/api/mobile/billing/payment/$paymentId").get().build())
    }

    suspend fun searchLaws(query: String): JSONObject = withContext(Dispatchers.IO) {
        val encoded = URLEncoder.encode(query, Charsets.UTF_8.name())
        executeJson(request("/api/mobile/laws/search?q=$encoded&limit=25").get().build())
    }

    suspend fun explainLaw(sectionId: String): JSONObject = withContext(Dispatchers.IO) {
        executeJson(request("/api/mobile/laws/$sectionId/explain").post(ByteArray(0).toRequestBody()).build())
    }

    suspend fun analyze(description: String, category: String, mode: String, files: List<Uri>): JSONObject = withContext(Dispatchers.IO) {
        val multipart = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("description", description)
            .addFormDataPart("case_category", category)
            .addFormDataPart("analysis_mode", mode)
            .addFormDataPart("consent", "accepted")
        files.forEach { uri ->
            val name = displayName(context.contentResolver, uri)
            val mime = context.contentResolver.getType(uri) ?: "application/octet-stream"
            multipart.addFormDataPart("files", name, UriRequestBody(context.contentResolver, uri, mime))
        }
        executeJson(request("/api/mobile/analyze").post(multipart.build()).build())
    }

    companion object {
        fun displayName(resolver: ContentResolver, uri: Uri): String {
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) return cursor.getString(0) ?: "document"
            }
            return uri.lastPathSegment ?: "document"
        }
    }
}

private class UriRequestBody(private val resolver: ContentResolver, private val uri: Uri, private val mime: String) : RequestBody() {
    override fun contentType() = mime.toMediaTypeOrNull()
    override fun contentLength(): Long {
        resolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst() && !cursor.isNull(0)) return cursor.getLong(0)
        }
        return -1
    }
    override fun writeTo(sink: BufferedSink) {
        val input = resolver.openInputStream(uri) ?: throw IOException("فایل قابل خواندن نیست.")
        input.use { source ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val count = source.read(buffer)
                if (count < 0) break
                sink.write(buffer, 0, count)
            }
        }
    }
}
