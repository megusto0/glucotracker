package com.local.glucotracker.ui.format

import kotlin.test.Test
import kotlin.test.assertEquals

class FoodIconTest {
    @Test
    fun theServerAnswerOutranksAnythingWorkedOutHere() {
        // The fridge decided for its own stock; this copy does not argue.
        assertEquals("🍲", foodIcon("Бутерброд с сыром", supplied = "🍲"))
        assertEquals("🥪", foodIcon("Бутерброд с сыром", supplied = "  "))
    }

    @Test
    fun theDiaryEntriesThatStartedThis() {
        assertEquals("🥪", foodIcon("Бутерброд с сыром и маслом"))
        assertEquals("🍲", foodIcon("Овсяная каша на молоке"))
        assertEquals("🍰", foodIcon("Сметанник"))
        assertEquals("🌯", foodIcon("Тако с курицей и сыром"))
    }

    @Test
    fun aDishIsReadBeforeItsIngredients() {
        // Matching «сыр» first would call a sandwich a cheese.
        assertEquals("🧀", foodIcon("Сыр полутвердый Брест-Литовск"))
        assertEquals("🧁", foodIcon("Сырок Топтыжка малиновый"))
    }

    @Test
    fun theRestaurantRowsGetSomethingToo() {
        assertEquals("🍔", foodIcon("Воппер Ролл"))
        assertEquals("🍗", foodIcon("Наггетсы (9 Шт)"))
        assertEquals("🍟", foodIcon("Картофель фри стандартный"))
    }

    @Test
    fun theUnknownGetsAParcelRatherThanAGuess() {
        assertEquals(FallbackFoodIcon, foodIcon("Нечто неопознанное"))
        assertEquals(FallbackFoodIcon, foodIcon(null, ""))
    }
}
