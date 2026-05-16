package com.local.glucotracker.ui.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.platform.app.InstrumentationRegistry
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GTTheme
import org.junit.Rule
import org.junit.Test

class NavigationShellInstrumentedTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun foodNavConfigRendersFourTabs() {
        compose.setContent {
            GTTheme {
                MainScaffold(
                    offlineBannerState = OfflineBannerUiState.Hidden,
                    navConfig = DefaultNavConfig,
                    navHost = { modifier, _ -> Box(modifier.testTag("main-content")) },
                )
            }
        }

        compose.onAllNodesWithTag("bottom-tab").assertCountEquals(4)
    }

    @Test
    fun fiveTabNavConfigRendersFiveTabs() {
        compose.setContent {
            GTTheme {
                MainScaffold(
                    offlineBannerState = OfflineBannerUiState.Hidden,
                    navConfig = FiveTabNavConfig,
                    navHost = { modifier, _ -> Box(modifier.testTag("main-content")) },
                )
            }
        }

        compose.onAllNodesWithTag("bottom-tab").assertCountEquals(5)
    }

    @Test
    fun pressingFabShowsActionOptions() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        compose.setContent {
            GTTheme {
                MainScaffold(
                    offlineBannerState = OfflineBannerUiState.Hidden,
                    navHost = { modifier, _ -> Box(modifier.testTag("main-content")) },
                )
            }
        }

        compose
            .onNodeWithContentDescription(context.getString(R.string.nav_capture_content_description))
            .performClick()

        compose.onNodeWithText(context.getString(R.string.fab_option_manual)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.fab_option_photo)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.fab_option_gallery)).assertIsDisplayed()
    }

    @Test
    fun offlineBannerRendersStateMachineCopies() {
        var bannerState by mutableStateOf<OfflineBannerUiState>(OfflineBannerUiState.Hidden)

        compose.setContent {
            GTTheme {
                MainScaffold(
                    offlineBannerState = bannerState,
                    navHost = { modifier, _ -> Box(modifier.testTag("main-content")) },
                )
            }
        }

        compose.onAllNodesWithText("Синхр. · 2 в очереди").assertCountEquals(0)

        compose.runOnUiThread {
            bannerState = OfflineBannerUiState.SyncQueue(queueDepth = 2)
        }
        compose.onNodeWithText("Синхр. · 2 в очереди").assertIsDisplayed()

        compose.runOnUiThread {
            bannerState = OfflineBannerUiState.OfflineStale(dataAt = "12:34")
        }
        compose.onNodeWithText("Нет сети · данные на 12:34").assertIsDisplayed()

        compose.runOnUiThread {
            bannerState = OfflineBannerUiState.OfflineQueue(queueDepth = 3)
        }
        compose.onNodeWithText("Нет сети · 3 в очереди · ждут отправки").assertIsDisplayed()

        compose.runOnUiThread {
            bannerState = OfflineBannerUiState.Hidden
        }
        compose.onAllNodesWithText("Нет сети · 3 в очереди · ждут отправки").assertCountEquals(0)
    }
}

private object FiveTabNavConfig : NavConfig {
    override val tabs = listOf(
        TabSpec(Route.Today.route, R.string.nav_today, NavIcon.Today),
        TabSpec("trend", R.string.stats_page_label, NavIcon.Trend),
        TabSpec(Route.History.route, R.string.nav_history, NavIcon.History),
        TabSpec(Route.Base.route, R.string.nav_base, NavIcon.Base),
        TabSpec(Route.More.route, R.string.nav_more, NavIcon.More),
    )
    override val captureSheetEntries = DefaultCaptureSheetEntries
    override val brand: BrandSpec? = null
}
