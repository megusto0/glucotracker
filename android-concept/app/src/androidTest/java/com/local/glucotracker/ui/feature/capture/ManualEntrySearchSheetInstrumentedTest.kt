package com.local.glucotracker.ui.feature.capture

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.platform.app.InstrumentationRegistry
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.ui.design.GTTheme
import org.junit.Rule
import org.junit.Test

class ManualEntrySearchSheetInstrumentedTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun returningFromRestaurantVariantsRestoresSearchWithoutCrash() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        compose.setContent {
            GTTheme {
                ManualEntrySearchSheetContent(
                    openCount = 3,
                    onDismiss = {},
                    onSubmitText = {},
                    onSubmitProduct = {},
                    onSubmitTemplate = {},
                    searchProducts = { _, _, _ -> },
                    searchTemplates = { _, _ -> },
                    initialTemplates = listOf(
                        template("nuggets-3", "Наггетсы 3 шт"),
                        template("nuggets-6", "Наггетсы 6 шт"),
                        template("nuggets-9", "Наггетсы 9 шт"),
                    ),
                )
            }
        }

        compose.onNodeWithText("Наггетсы").performClick()
        compose.onNodeWithTag("restaurant-variant-picker").assertIsDisplayed()
        compose
            .onNode(SemanticsMatcher.keyIsDefined(SemanticsProperties.ProgressBarRangeInfo))
            .performSemanticsAction(SemanticsActions.SetProgress) { setProgress ->
                setProgress(2f)
            }
        compose.onNodeWithText(context.getString(R.string.restaurant_variant_back)).performClick()
        compose.onNodeWithTag("manual-entry-search-sheet").assertIsDisplayed()
    }

    private fun template(id: String, name: String) =
        Template(
            id = id,
            prefix = "rostics",
            name = name,
            aliases = emptyList(),
            imageUrl = null,
            defaultKcal = 100.0,
            defaultCarbsG = 10.0,
            defaultProteinG = 8.0,
            defaultFatG = 5.0,
            defaultFiberG = 0.0,
            defaultGrams = 100.0,
            usageCount = 0,
            lastUsedAt = null,
        )
}
