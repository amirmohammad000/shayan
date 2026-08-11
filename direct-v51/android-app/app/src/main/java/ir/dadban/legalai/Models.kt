package ir.dadban.legalai

import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject

enum class AppScreen { AUTH, PROFILE, HOME, ANALYZE, RESULT, LAW_BOOK, PREMIUM }

data class UserProfile(
    val phone: String = "",
    val fullName: String = "",
    val province: String = "",
    val city: String = "",
    val completed: Boolean = false
) {
    companion object {
        fun fromJson(json: JSONObject?): UserProfile {
            if (json == null) return UserProfile()
            return UserProfile(
                phone = json.optString("phone"),
                fullName = json.optString("full_name"),
                province = json.optString("province"),
                city = json.optString("city"),
                completed = json.optBoolean("profile_completed", false)
            )
        }
    }
}

data class Entitlements(
    val isPremium: Boolean = false,
    val planCode: String = "free",
    val subscriptionExpiresAt: Long? = null,
    val freeBasicRemaining: Int = 3,
    val premiumBasicRemaining: Int = 0,
    val premiumDetailedRemaining: Int = 0,
    val premiumPleadingRemaining: Int = 0
) {
    companion object {
        fun fromJson(json: JSONObject?): Entitlements {
            if (json == null) return Entitlements()
            return Entitlements(
                isPremium = json.optBoolean("is_premium", false),
                planCode = json.optString("plan_code", "free"),
                subscriptionExpiresAt = json.optLong("subscription_expires_at").takeIf { it > 0 },
                freeBasicRemaining = json.optInt("free_basic_remaining", 0),
                premiumBasicRemaining = json.optInt("premium_basic_remaining", 0),
                premiumDetailedRemaining = json.optInt("premium_detailed_remaining", 0),
                premiumPleadingRemaining = json.optInt("premium_pleading_remaining", 0)
            )
        }
    }
}

data class LawItem(
    val sectionId: String,
    val title: String,
    val article: String,
    val text: String,
    val authority: String,
    val legalStatus: String,
    val sourceUrl: String
) {
    companion object {
        fun fromJson(obj: JSONObject): LawItem = LawItem(
            sectionId = obj.optString("section_id"),
            title = obj.optString("title"),
            article = obj.optString("article"),
            text = obj.optString("text"),
            authority = obj.optString("authority"),
            legalStatus = obj.optString("legal_status"),
            sourceUrl = obj.optString("source_url")
        )

        fun list(array: JSONArray?): List<LawItem> {
            if (array == null) return emptyList()
            return (0 until array.length()).mapNotNull { array.optJSONObject(it) }.map(::fromJson)
        }
    }
}

data class UiState(
    val screen: AppScreen = AppScreen.AUTH,
    val loading: Boolean = false,
    val message: String? = null,
    val phone: String = "",
    val challengeId: String? = null,
    val devCode: String? = null,
    val profile: UserProfile = UserProfile(),
    val entitlements: Entitlements = Entitlements(),
    val description: String = "",
    val category: String = "کیفری",
    val analysisMode: String = "basic",
    val consent: Boolean = true,
    val selectedFiles: List<Uri> = emptyList(),
    val resultJson: String? = null,
    val lawQuery: String = "",
    val lawResults: List<LawItem> = emptyList(),
    val selectedLaw: LawItem? = null,
    val lawExplanation: JSONObject? = null,
    val pendingPaymentId: String? = null,
    val paymentUrl: String? = null
)
