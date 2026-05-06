package com.local.glucotracker.data.api

import com.local.glucotracker.generated.api.DashboardApi
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class TodayApiMockEngineTest {
    @Test
    fun getTodayDecodesDashboardTodayFixture() = runTest {
        val engine = MockEngine { request ->
            assertEquals("/dashboard/today", request.url.encodedPath)
            respond(
                content = DashboardTodayJson,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, "application/json"),
            )
        }
        val api = TodayApi(
            DashboardApi(
                baseUrl = "http://localhost",
                httpClientEngine = engine,
            ),
        )

        val today = api.getToday()

        assertEquals(LocalDate.parse("2026-05-05"), today.date)
        assertEquals(1780, today.kcal.toInt())
        assertEquals(4, today.mealCount)
        assertEquals(212.5, today.carbsG.toDouble(), 0.0)
    }

    private companion object {
        const val DashboardTodayJson = """
            {
              "date": "2026-05-05",
              "kcal": 1780,
              "carbs_g": 212.5,
              "protein_g": 82,
              "fat_g": 61.5,
              "fiber_g": 24,
              "meal_count": 4,
              "week_avg_kcal": 1812,
              "prev_week_avg_kcal": 1760,
              "week_avg_carbs": 198.5,
              "prev_week_avg_carbs": 205,
              "hours_since_last_meal": 2.5,
              "last_meal_at": "2026-05-05T13:10:00Z",
              "nutrients": []
            }
        """
    }
}
