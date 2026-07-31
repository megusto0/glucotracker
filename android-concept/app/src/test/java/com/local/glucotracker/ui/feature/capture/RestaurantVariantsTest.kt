package com.local.glucotracker.ui.feature.capture

import com.local.glucotracker.domain.model.Template
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class RestaurantVariantsTest {
    @Test
    fun nuggetsAreGroupedPerRestaurantWithDiscreteQuantities() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("r3", "rostics", "Наггетсы 3 шт"),
                template("r6", "rostics", "Наггетсы 6 шт"),
                template("r9", "rostics", "Наггетсы 9 шт"),
                template("b3", "bk", "Наггетсы (3 Шт)"),
                template("b6", "bk", "Наггетсы (6 Шт)"),
                template("b9", "bk", "Наггетсы (9 Шт)"),
            ),
        )

        assertEquals(2, choices.size)
        val groups = choices.map { assertIs<RestaurantTemplateChoice.Variants>(it).group }
        val rostics = groups.first { it.prefix == "rostics" }
        val burgerKing = groups.first { it.prefix == "bk" }
        assertEquals("Наггетсы", rostics.name)
        assertEquals(listOf(3, 6, 9), rostics.quantityOptions)
        assertTrue(rostics.hasQuantitySlider)
        assertEquals("r6", variantForQuantity(rostics, 6)?.id)
        assertEquals(listOf(3, 6, 9), burgerKing.quantityOptions)
    }

    @Test
    fun whopperFamilyIsOneChoiceWithNamedVariantsButRollStaysSeparate() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("base", "bk", "Воппер"),
                template("cheese", "bk", "Воппер С Сыром"),
                template("double", "bk", "Двойной Воппер"),
                template("spicy", "bk", "Острый Воппер"),
                template("roll", "bk", "Воппер Ролл"),
            ),
        )

        val group = choices
            .filterIsInstance<RestaurantTemplateChoice.Variants>()
            .single()
            .group
        assertEquals("Воппер", group.name)
        assertEquals(4, group.variants.size)
        assertFalse(group.hasQuantitySlider)
        assertTrue(
            choices.filterIsInstance<RestaurantTemplateChoice.Single>()
                .any { it.template.id == "roll" },
        )
    }

    @Test
    fun equalQuantityFamiliesWithDifferentSeasoningStaySeparate() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("plain3", "bk", "Наггетсы (3 шт)"),
                template("plain6", "bk", "Наггетсы (6 шт)"),
                template("spicy3", "bk", "Острые наггетсы (3 шт)"),
                template("spicy6", "bk", "Острые наггетсы (6 шт)"),
            ),
        )

        assertEquals(2, choices.filterIsInstance<RestaurantTemplateChoice.Variants>().size)
    }

    @Test
    fun onionRingsAndCheeseMedallionsUseIndependentQuantitySliders() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("onion3", "bk", "Луковые Кольца (3 Шт)"),
                template("onion6", "bk", "Луковые Кольца (6 Шт)"),
                template("cheese3", "bk", "Сырные Медальоны (3 Шт)"),
                template("cheese6", "bk", "Сырные Медальоны (6 Шт)"),
            ),
        )

        val groups = choices.filterIsInstance<RestaurantTemplateChoice.Variants>()
            .map { it.group }
        assertEquals(2, groups.size)
        assertTrue(groups.all { it.hasQuantitySlider })
        assertEquals(
            setOf("Луковые Кольца", "Сырные Медальоны"),
            groups.map { it.name }.toSet(),
        )
    }

    @Test
    fun rostmastersAndBitesUseNamedVariantCards() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("original", "rostics", "Ростмастер оригинальный"),
                template("spicy", "rostics", "Ростмастер острый"),
                template("smart", "rostics", "Ростмастер Блю Чиз Смарт"),
                template("bites-small", "rostics", "Байтсы из куриного филе, малые"),
                template("bites-large", "rostics", "Байтсы из куриного филе, большие"),
            ),
        )

        val groups = choices.filterIsInstance<RestaurantTemplateChoice.Variants>()
            .map { it.group }
        assertEquals(setOf("Ростмастер", "Байтсы"), groups.map { it.name }.toSet())
        assertTrue(groups.none { it.hasQuantitySlider })
    }

    private fun template(id: String, prefix: String, name: String) =
        Template(
            id = id,
            prefix = prefix,
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
