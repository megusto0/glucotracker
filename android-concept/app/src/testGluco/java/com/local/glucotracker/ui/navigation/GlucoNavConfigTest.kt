package com.local.glucotracker.ui.navigation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class GlucoNavConfigTest {
    @Test
    fun bottomTabsKeepBaseOutOfPrimaryNavigation() {
        val routes = GlucoNavConfig.tabs.map { it.route }

        assertEquals(
            listOf(Route.Today.route, "glucose", Route.History.route, Route.More.route),
            routes,
        )
        assertFalse(Route.Base.route in routes)
    }
}
