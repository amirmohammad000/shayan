from pathlib import Path
root = Path('android-app')

def repl(rel, old, new):
    p = root / rel
    s = p.read_text(encoding='utf-8')
    if old not in s:
        raise SystemExit(f'missing pattern in {rel}: {old[:80]!r}')
    p.write_text(s.replace(old, new), encoding='utf-8')

repl('app/build.gradle.kts', 'versionCode = 5\n        versionName = "0.5.0"', 'versionCode = 6\n        versionName = "0.6.0"')
repl('gradle.properties', 'LEGAL_DEBUG_API_BASE_URL=http://10.0.2.2:8000/', 'LEGAL_DEBUG_API_BASE_URL=https://example.invalid/')

repl('app/src/main/java/ir/dadban/legalai/ApiClient.kt',
'''    private val base = BuildConfig.API_BASE_URL.trimEnd('/')\n\n    private fun request(path: String): Request.Builder {\n        val builder = Request.Builder().url(base + path).header("Accept", "application/json")''',
'''    private val serverConfig = ServerConfig(context)\n\n    private fun base(): String = serverConfig.current().trimEnd('/')\n\n    private fun request(path: String): Request.Builder {\n        val builder = Request.Builder().url(base() + path).header("Accept", "application/json")''')
repl('app/src/main/java/ir/dadban/legalai/ApiClient.kt',
'''    private fun jsonBody(json: JSONObject): RequestBody =\n        json.toString().toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())\n''',
'''    private fun jsonBody(json: JSONObject): RequestBody =\n        json.toString().toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())\n\n    suspend fun testServer(rawBaseUrl: String): JSONObject = withContext(Dispatchers.IO) {\n        val candidate = ServerConfig.normalize(rawBaseUrl).trimEnd('/')\n        val request = Request.Builder()\n            .url(candidate + "/health")\n            .header("Accept", "application/json")\n            .get()\n            .build()\n        client.newCall(request).execute().use { response ->\n            val text = response.body?.string().orEmpty()\n            val json = runCatching { JSONObject(text) }.getOrElse { JSONObject() }\n            if (!response.isSuccessful) {\n                val detail = json.optString("detail").ifBlank { "سرور پاسخ معتبر نداد (${response.code})" }\n                throw ApiException(response.code, detail)\n            }\n            json\n        }\n    }\n''')

repl('app/src/main/java/ir/dadban/legalai/Models.kt',
'''    val loading: Boolean = false,\n    val message: String? = null,\n    val phone: String = "",''',
'''    val loading: Boolean = false,\n    val message: String? = null,\n    val serverUrl: String = BuildConfig.API_BASE_URL,\n    val serverConnected: Boolean? = null,\n    val phone: String = "",''')

repl('app/src/main/java/ir/dadban/legalai/MainViewModel.kt',
'''    private val tokenStore = SecureTokenStore(application)\n    private val api = ApiClient(application, tokenStore)\n\n    var state by mutableStateOf(UiState())''',
'''    private val tokenStore = SecureTokenStore(application)\n    private val serverConfig = ServerConfig(application)\n    private val api = ApiClient(application, tokenStore)\n\n    var state by mutableStateOf(UiState(serverUrl = serverConfig.current()))''')
repl('app/src/main/java/ir/dadban/legalai/MainViewModel.kt',
'''    fun setPhone(v: String) { state = state.copy(phone = v, message = null) }\n    fun setDescription(v: String) { state = state.copy(description = v) }''',
'''    fun setPhone(v: String) { state = state.copy(phone = v, message = null) }\n    fun setServerUrl(v: String) { state = state.copy(serverUrl = v, serverConnected = null, message = null) }\n\n    fun testAndSaveServer() = launchAction {\n        val normalized = ServerConfig.normalize(state.serverUrl)\n        api.testServer(normalized)\n        serverConfig.save(normalized)\n        state = state.copy(serverUrl = normalized, serverConnected = true, message = "اتصال به سرور برقرار شد.")\n    }\n    fun setDescription(v: String) { state = state.copy(description = v) }''')
repl('app/src/main/java/ir/dadban/legalai/MainViewModel.kt',
'''    fun resetAuth() { state = UiState(screen = AppScreen.AUTH, phone = state.phone) }''',
'''    fun resetAuth() { state = UiState(screen = AppScreen.AUTH, phone = state.phone, serverUrl = state.serverUrl, serverConnected = state.serverConnected) }''')
repl('app/src/main/java/ir/dadban/legalai/MainViewModel.kt',
'''    fun requestOtp() = launchAction {\n        val response = api.requestOtp(state.phone)''',
'''    fun requestOtp() = launchAction {\n        val normalized = serverConfig.save(state.serverUrl)\n        state = state.copy(serverUrl = normalized)\n        val response = api.requestOtp(state.phone)''')
repl('app/src/main/java/ir/dadban/legalai/MainViewModel.kt',
'''        state = UiState(screen = AppScreen.AUTH)''',
'''        state = UiState(screen = AppScreen.AUTH, serverUrl = serverConfig.current())''')
repl('app/src/main/java/ir/dadban/legalai/MainViewModel.kt',
'''                    state = UiState(screen = AppScreen.AUTH, message = "نشست شما منقضی شده است؛ دوباره وارد شوید.")''',
'''                    state = UiState(screen = AppScreen.AUTH, serverUrl = serverConfig.current(), message = "نشست شما منقضی شده است؛ دوباره وارد شوید.")''')

repl('app/src/main/java/ir/dadban/legalai/MainActivity.kt',
'''        Spacer(Modifier.height(28.dp))\n        if (state.challengeId == null) {\n            OutlinedTextField(\n                value = state.phone,''',
'''        Spacer(Modifier.height(20.dp))\n        if (state.challengeId == null) {\n            OutlinedTextField(\n                value = state.serverUrl,\n                onValueChange = vm::setServerUrl,\n                modifier = Modifier.fillMaxWidth(),\n                label = { Text("آدرس Backend") },\n                placeholder = { Text("https://api.example.com") },\n                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),\n                singleLine = true\n            )\n            Spacer(Modifier.height(8.dp))\n            OutlinedButton(onClick = vm::testAndSaveServer, modifier = Modifier.fillMaxWidth()) { Text("تست و ذخیره اتصال") }\n            state.serverConnected?.let { connected ->\n                Spacer(Modifier.height(6.dp))\n                Text(if (connected) "✓ سرور در دسترس است" else "سرور هنوز تست نشده است", color = MaterialTheme.colorScheme.onSurfaceVariant)\n            }\n            Spacer(Modifier.height(16.dp))\n            OutlinedTextField(\n                value = state.phone,''')

p = root / 'app/src/main/java/ir/dadban/legalai/ServerConfig.kt'
p.write_text('''package ir.dadban.legalai\n\nimport android.content.Context\nimport java.net.URI\n\nclass ServerConfig(context: Context) {\n    private val prefs = context.getSharedPreferences("dadban_server", Context.MODE_PRIVATE)\n\n    fun current(): String = prefs.getString(KEY_BASE_URL, null)?.let(::normalize) ?: normalize(BuildConfig.API_BASE_URL)\n\n    fun save(raw: String): String {\n        val normalized = normalize(raw)\n        prefs.edit().putString(KEY_BASE_URL, normalized).apply()\n        return normalized\n    }\n\n    companion object {\n        private const val KEY_BASE_URL = "api_base_url"\n\n        fun normalize(raw: String): String {\n            var value = raw.trim()\n            require(value.isNotBlank()) { "آدرس سرور را وارد کنید." }\n            if (!value.startsWith("http://", true) && !value.startsWith("https://", true)) {\n                value = "https://$value"\n            }\n            val uri = runCatching { URI(value) }.getOrNull()\n                ?: throw IllegalArgumentException("آدرس سرور معتبر نیست.")\n            require(uri.scheme == "https" || uri.scheme == "http") { "آدرس سرور باید با http یا https باشد." }\n            require(!uri.host.isNullOrBlank()) { "نام میزبان سرور معتبر نیست." }\n            return value.trimEnd('/') + "/"\n        }\n    }\n}\n''', encoding='utf-8')
