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
        assertEquals(setOf("Ростмастер", "Байтсы из куриного филе"), groups.map { it.name }.toSet())
        assertTrue(groups.none { it.hasQuantitySlider })
        assertFalse(groups.single { it.name == "Ростмастер" }.hasSizeSlider)
        assertEquals(
            listOf("bites-small", "bites-large"),
            groups.single { it.name != "Ростмастер" }.sizeOptions.map { it.id },
        )
    }

    @Test
    fun friesGetOneSizeRulerPerRestaurant() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("bk-l", "bk", "Кинг Фри Большой"),
                template("bk-maxx", "bk", "Кинг Фри MAXX"),
                template("bk-hot-s", "bk", "Острый Кинг Фри малый"),
                template("bk-hot-maxx", "bk", "Острый Кинг Фри MAXX"),
                template("bk-s", "bk", "Кинг Фри Малый"),
                template("bk-m", "bk", "Кинг Фри Стандартный"),
                template("bk-seasoned", "bk", "Кинг Фри Стандартный + Приправа «Сметана И Лук»"),
                template("r-basket", "rostics", "Картофель фри баскет"),
                template("r-s", "rostics", "Картофель фри малый"),
                template("r-m", "rostics", "Картофель фри средний"),
                template("v-double", "vit", "Картофель фри двойной"),
                template("v-l", "vit", "Картофель фри большой"),
                template("v-s", "vit", "Картофель фри маленький"),
                template("v-m", "vit", "Картофель фри средний"),
            ),
        )

        val groups = choices.filterIsInstance<RestaurantTemplateChoice.Variants>()
            .filter { it.group.prefix != "bk" }
            .associate { it.group.prefix to it.group }
        val bk = choices.filterIsInstance<RestaurantTemplateChoice.Variants>()
            .map { it.group }
            .filter { it.prefix == "bk" }
            .associateBy { it.name }
        assertEquals(listOf("bk-s", "bk-m", "bk-l", "bk-maxx"), bk.getValue("Кинг Фри").sizeOptions.map { it.id })
        assertEquals(listOf("bk-hot-s", "bk-hot-maxx"), bk.getValue("Острый Кинг Фри").sizeOptions.map { it.id })
        assertEquals(listOf("r-s", "r-m", "r-basket"), groups.getValue("rostics").sizeOptions.map { it.id })
        assertEquals(
            listOf("v-s", "v-m", "v-l", "v-double"),
            groups.getValue("vit").sizeOptions.map { it.id },
        )
        assertTrue(
            choices.filterIsInstance<RestaurantTemplateChoice.Single>()
                .any { it.template.id == "bk-seasoned" },
        )
    }

    @Test
    fun countryPotatoesAreTheirOwnRulerNextToFries() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("fries-s", "rostics", "Картофель фри малый"),
                template("fries-m", "rostics", "Картофель фри средний"),
                template("country-s", "rostics", "Картофель по-деревенски малый"),
                template("country-m", "rostics", "Картофель по-деревенски средний"),
            ),
        )

        val names = choices.filterIsInstance<RestaurantTemplateChoice.Variants>()
            .map { it.group.name }
        assertEquals(setOf("Картофель фри", "Картофель по-деревенски"), names.toSet())
    }

    @Test
    fun drinksGroupBySizeWordOrVolumeAndDoubleBurgersStayApart() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("lj", "bk", "Липтон Грин Джуниор 0.3"),
                template("ls", "bk", "Липтон Грин Малый 0.4 Л"),
                template("lm", "bk", "Липтон Грин Стандартный"),
                template("lxl", "bk", "Липтон Грин Xl 1,0 Л"),
                template("c3", "rostics", "Эвервесс Кола 0,3 л"),
                template("c5", "rostics", "Эвервесс Кола 0,5 л"),
                template("c8", "rostics", "Эвервесс Кола 0,8 л"),
                template("angus", "bk", "Ангус Шеф"),
                template("angus2", "bk", "Ангус Шеф Двойной"),
            ),
        )

        val groups = choices.filterIsInstance<RestaurantTemplateChoice.Variants>()
            .associate { it.group.name to it.group }
        assertEquals(listOf("lj", "ls", "lm", "lxl"), groups.getValue("Липтон Грин").sizeOptions.map { it.id })
        assertEquals(listOf("c3", "c5", "c8"), groups.getValue("Эвервесс Кола").sizeOptions.map { it.id })
        assertEquals(0.5, restaurantSize("Эвервесс Кола 0,5 л")?.liters)
        assertEquals(null, restaurantSize("Ангус Шеф Двойной"))
        assertEquals(setOf("Липтон Грин", "Эвервесс Кола"), groups.keys)
    }

    @Test
    fun vitBreakfastFamiliesUseOneChoicePerDishWithNamedFillings() {
        val choices = restaurantTemplateChoices(
            listOf(
                template("omelet", "vit", "Омлет"),
                template("omelet-bacon", "vit", "Омлет с беконом"),
                template("omelet-cheese", "vit", "Омлет с сыром"),
                template("eggs", "vit", "Яичница"),
                template("eggs-ham", "vit", "Яичница с ветчиной"),
                template("muffin-bacon", "vit", "Маффин с яйцом и беконом"),
                template("muffin-cheese", "vit", "Маффин с яйцом и сыром"),
                template("omletter", "vit", "Омлеттер с беконом и сыром"),
                template("strips3", "vit", "Стрипсы (3 шт.)"),
                template("strips5", "vit", "Стрипсы (5 шт.)"),
            ),
        )

        val groups = choices.filterIsInstance<RestaurantTemplateChoice.Variants>()
            .map { it.group }
        assertEquals(
            setOf("Омлет", "Яичница", "Маффин с яйцом", "Стрипсы"),
            groups.map { it.name }.toSet(),
        )
        assertTrue(groups.filter { it.name != "Стрипсы" }.all { !it.hasQuantitySlider })
        assertEquals(listOf(3, 5), groups.single { it.name == "Стрипсы" }.quantityOptions)
        assertTrue(
            choices.filterIsInstance<RestaurantTemplateChoice.Single>()
                .any { it.template.id == "omletter" },
        )
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
