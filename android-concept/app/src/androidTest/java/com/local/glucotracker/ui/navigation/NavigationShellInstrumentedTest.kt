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
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
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
    fun pressingFabShowsCaptureSheet() {
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

        compose.onNodeWithTag("capture-sheet").assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.capture_sheet_title)).assertIsDisplayed()
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
