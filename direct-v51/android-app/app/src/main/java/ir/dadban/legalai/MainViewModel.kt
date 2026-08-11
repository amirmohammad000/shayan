package ir.dadban.legalai

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import org.json.JSONObject

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val tokenStore = SecureTokenStore(application)
    private val api = ApiClient(application, tokenStore)

    var state by mutableStateOf(UiState())
        private set

    init {
        if (tokenStore.load() != null) refreshAccount() else state = state.copy(screen = AppScreen.AUTH)
    }

    fun setPhone(v: String) { state = state.copy(phone = v, message = null) }
    fun setDescription(v: String) { state = state.copy(description = v) }
    fun setCategory(v: String) { state = state.copy(category = v) }
    fun setMode(v: String) { state = state.copy(analysisMode = v, message = null) }
    fun setFiles(v: List<Uri>) { state = state.copy(selectedFiles = v.take(5)) }
    fun setLawQuery(v: String) { state = state.copy(lawQuery = v) }
    fun dismissMessage() { state = state.copy(message = null) }
    fun resetAuth() { state = UiState(screen = AppScreen.AUTH, phone = state.phone) }
    fun go(screen: AppScreen) { state = state.copy(screen = screen, message = null) }


    fun loginWithPhone() {
        if (state.phone.filter(Char::isDigit).length < 11) {
            state = state.copy(message = "شماره همراه را کامل وارد کنید.")
            return
        }
        launchAction {
            val response = api.phoneLogin(state.phone)
            tokenStore.save(response.getString("access_token"))
            applyAccount(response)
            val completed = response.optBoolean("profile_completed", state.profile.completed)
            state = state.copy(
                screen = if (completed) AppScreen.HOME else AppScreen.PROFILE,
                challengeId = null, devCode = null, message = null
            )
        }
    }

    fun requestOtp() = launchAction {
        val response = api.requestOtp(state.phone)
        state = state.copy(
            challengeId = response.getString("challenge_id"),
            devCode = response.optString("dev_code").takeIf { it.isNotBlank() },
            message = "کد ورود ارسال شد."
        )
    }

    fun verifyOtp(code: String) = launchAction {
        val challenge = state.challengeId ?: throw IllegalStateException("ابتدا کد درخواست کنید.")
        val response = api.verifyOtp(challenge, code)
        tokenStore.save(response.getString("access_token"))
        applyAccount(response)
        val completed = response.optBoolean("profile_completed", state.profile.completed)
        state = state.copy(
            screen = if (completed) AppScreen.HOME else AppScreen.PROFILE,
            challengeId = null, devCode = null, message = null
        )
    }

    fun refreshAccount() = launchAction(onUnauthorized = true) {
        val response = api.me()
        applyAccount(response)
        val completed = response.optBoolean("profile_completed", state.profile.completed)
        if (state.screen == AppScreen.AUTH) state = state.copy(screen = if (completed) AppScreen.HOME else AppScreen.PROFILE)
    }

    fun saveProfile(fullName: String, province: String, city: String) {
        if (fullName.trim().length < 3) {
            state = state.copy(message = "نام و نام خانوادگی را کامل وارد کنید.")
            return
        }
        launchAction {
            val response = api.saveProfile(fullName.trim(), province.trim(), city.trim())
            state = state.copy(
                profile = UserProfile.fromJson(response.optJSONObject("profile")),
                entitlements = Entitlements.fromJson(response.optJSONObject("entitlements")),
                screen = AppScreen.HOME,
                message = "پروفایل ذخیره شد."
            )
        }
    }

    fun logout() = viewModelScope.launch {
        runCatching { api.logout() }
        tokenStore.clear()
        state = UiState(screen = AppScreen.AUTH)
    }

    fun startNewAnalysis(mode: String = "basic") {
        if (mode != "basic" && !state.entitlements.isPremium) {
            state = state.copy(screen = AppScreen.PREMIUM, message = "این خدمت فقط برای حساب پریمیوم فعال است.")
            return
        }
        state = state.copy(screen = AppScreen.ANALYZE, analysisMode = mode, description = "", selectedFiles = emptyList(), resultJson = null)
    }

    fun analyze() {
        val desc = state.description.trim()
        if (desc.length < 5 && state.selectedFiles.isEmpty()) {
            state = state.copy(message = "مشکل را توضیح دهید یا یک رأی/ابلاغیه بارگذاری کنید.")
            return
        }
        if (state.analysisMode != "basic" && !state.entitlements.isPremium) {
            state = state.copy(message = "این خدمت فقط برای حساب پریمیوم فعال است.", screen = AppScreen.PREMIUM)
            return
        }
        launchAction {
            val effectiveDescription = if (desc.isBlank()) "این سند را به زبان ساده تحلیل و بر اساس قوانین معتبر ایران بررسی کن." else desc
            val response = api.analyze(effectiveDescription, state.category, state.analysisMode, state.selectedFiles)
            val entitlements = Entitlements.fromJson(response.optJSONObject("meta")?.optJSONObject("entitlements"))
            state = state.copy(resultJson = response.toString(), entitlements = entitlements, screen = AppScreen.RESULT, message = null)
        }
    }

    fun searchLaws() {
        if (state.lawQuery.trim().length < 2) {
            state = state.copy(message = "حداقل دو نویسه برای جست‌وجو وارد کنید.")
            return
        }
        launchAction {
            val response = api.searchLaws(state.lawQuery.trim())
            state = state.copy(lawResults = LawItem.list(response.optJSONArray("results")), selectedLaw = null, lawExplanation = null)
        }
    }

    fun selectLaw(item: LawItem) { state = state.copy(selectedLaw = item, lawExplanation = null) }
    fun clearSelectedLaw() { state = state.copy(selectedLaw = null, lawExplanation = null) }

    fun explainSelectedLaw() {
        val item = state.selectedLaw ?: return
        launchAction {
            val response = api.explainLaw(item.sectionId)
            state = state.copy(lawExplanation = response.optJSONObject("explanation"))
        }
    }

    fun startCheckout(onUrl: (String) -> Unit) = launchAction {
        val response = api.checkout()
        val url = response.getString("redirect_url")
        state = state.copy(pendingPaymentId = response.getString("payment_id"), paymentUrl = url, message = "پس از پرداخت به برنامه برگردید و وضعیت را بررسی کنید.")
        onUrl(url)
    }

    fun checkPayment() {
        val id = state.pendingPaymentId ?: run { refreshAccount(); return }
        launchAction {
            val response = api.paymentStatus(id)
            val paid = response.getJSONObject("payment").optString("status") == "paid"
            state = state.copy(
                entitlements = Entitlements.fromJson(response.optJSONObject("entitlements")),
                message = if (paid) "اشتراک پریمیوم فعال شد." else "پرداخت هنوز تأیید نشده است.",
                pendingPaymentId = if (paid) null else id,
                paymentUrl = if (paid) null else state.paymentUrl
            )
        }
    }

    private fun applyAccount(response: JSONObject) {
        val user = response.optJSONObject("user")
        state = state.copy(
            profile = UserProfile.fromJson(user?.optJSONObject("profile")),
            entitlements = Entitlements.fromJson(response.optJSONObject("entitlements"))
        )
    }

    private fun launchAction(onUnauthorized: Boolean = false, block: suspend () -> Unit) {
        viewModelScope.launch {
            state = state.copy(loading = true, message = null)
            try {
                block()
            } catch (e: ApiException) {
                if (e.statusCode == 401 && onUnauthorized) {
                    tokenStore.clear()
                    state = UiState(screen = AppScreen.AUTH, message = "نشست شما منقضی شده است؛ دوباره وارد شوید.")
                } else {
                    state = state.copy(message = e.message ?: "خطای سرور")
                }
            } catch (e: Exception) {
                state = state.copy(message = e.message ?: "خطای پیش‌بینی‌نشده")
            } finally {
                state = state.copy(loading = false)
            }
        }
    }
}
