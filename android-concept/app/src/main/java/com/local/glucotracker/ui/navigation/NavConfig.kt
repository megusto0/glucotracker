package com.local.glucotracker.ui.navigation

import androidx.annotation.StringRes
import androidx.annotation.DrawableRes
import androidx.compose.ui.graphics.Color
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import com.local.glucotracker.R

interface NavConfig {
    val tabs: List<TabSpec>
    val captureSheetEntries: List<CaptureEntrySpec>
    val brand: BrandSpec?
}

data class BrandSpec(
    @DrawableRes val mark: Int,
    @StringRes val name: Int,
    val activeIndicatorColor: Color,
)

data class TabSpec(
    val route: String,
    @StringRes val label: Int,
    val icon: NavIcon,
)

data class CaptureEntrySpec(
    val kind: CaptureEntryKind,
    @StringRes val title: Int,
    @StringRes val subtitle: Int,
)

enum class NavIcon {
    Today,
    Trend,
    History,
    Base,
    More,
}

enum class CaptureEntryKind {
    Photo,
    Gallery,
    Text,
    Template,
}

val DefaultCaptureSheetEntries = listOf(
    CaptureEntrySpec(
        kind = CaptureEntryKind.Photo,
        title = R.string.capture_photo_title,
        subtitle = R.string.capture_photo_subtitle,
    ),
    CaptureEntrySpec(
        kind = CaptureEntryKind.Gallery,
        title = R.string.capture_gallery_title,
        subtitle = R.string.capture_gallery_subtitle,
    ),
    CaptureEntrySpec(
        kind = CaptureEntryKind.Text,
        title = R.string.capture_text_title,
        subtitle = R.string.capture_text_subtitle,
    ),
    CaptureEntrySpec(
        kind = CaptureEntryKind.Template,
        title = R.string.capture_template_title,
        subtitle = R.string.capture_template_subtitle,
    ),
)

object DefaultNavConfig : NavConfig {
    override val tabs = listOf(
        TabSpec(Route.Today.route, R.string.nav_today, NavIcon.Today),
        TabSpec(Route.History.route, R.string.nav_history, NavIcon.History),
        TabSpec(Route.Base.route, R.string.nav_base, NavIcon.Base),
        TabSpec(Route.More.route, R.string.nav_more, NavIcon.More),
    )
    override val captureSheetEntries = DefaultCaptureSheetEntries
    override val brand: BrandSpec? = null
}

interface FlavorNavGraph {
    fun NavGraphBuilder.registerFlavorRoutes(navController: NavHostController)
}

object NoopFlavorNavGraph : FlavorNavGraph {
    override fun NavGraphBuilder.registerFlavorRoutes(navController: NavHostController) = Unit
}
