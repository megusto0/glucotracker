package com.local.glucotracker.ui.feature.capture

import com.local.glucotracker.domain.model.Template

internal data class RestaurantVariantGroup(
    val id: String,
    val prefix: String,
    val name: String,
    val variants: List<Template>,
) {
    val imageUrl: String?
        get() = variants.firstNotNullOfOrNull { variant -> variant.imageUrl }

    val quantityOptions: List<Int>
        get() = variants.mapNotNull { variant -> restaurantQuantity(variant.name) }.distinct().sorted()

    val hasQuantitySlider: Boolean
        get() = quantityOptions.size == variants.size && quantityOptions.size > 1

    /**
     * One step per portion size, smallest first — the fries ruler. Only when
     * every variant names its size and no two land on the same step; anything
     * looser falls back to the list of named variants.
     */
    val sizeOptions: List<Template>
        get() {
            if (hasQuantitySlider || variants.size < 2) return emptyList()
            val sizes = variants.map { restaurantSize(it.name) ?: return emptyList() }
            if (sizes.distinctBy { it.order }.size != sizes.size) return emptyList()
            return variants.sortedBy { restaurantSize(it.name)?.order }
        }

    val hasSizeSlider: Boolean
        get() = sizeOptions.isNotEmpty()
}

/**
 * The size a restaurant gives a portion in its name: "Кинг Фри Большой",
 * "Картофель по-деревенски средний", "Эвервесс Кола 0,5 л".
 *
 * [word] is the size as the restaurant spells it; [liters] is the drink volume
 * when the name carries one. [order] sorts the steps of one family.
 */
internal data class RestaurantSize(
    val word: String?,
    val rank: Int?,
    val liters: Double?,
) {
    val order: Double
        get() = (rank ?: 0) * 10.0 + (liters ?: 0.0)
}

internal sealed interface RestaurantTemplateChoice {
    val id: String

    data class Single(val template: Template) : RestaurantTemplateChoice {
        override val id: String = "template:${template.id}"
    }

    data class Variants(val group: RestaurantVariantGroup) : RestaurantTemplateChoice {
        override val id: String = group.id
    }
}

private val RestaurantPrefixes = setOf("bk", "rostics", "vit", "mc", "kfc")
private val QuantityPattern = Regex("""(?iu)\(?\b(\d+)\s*шт\.?\)?""")
private val StandaloneWhopperPattern = Regex("""(?iu)(^|\s)воппер($|\s)""")
private val NonWordPattern = Regex("""[^\p{L}\p{N}]+""")

/** Size words, smallest first. "Двойной" counts only for potatoes, see below. */
private val SizeRanks = linkedMapOf(
    "джуниор" to 0,
    "малый" to 1, "малая" to 1, "малые" to 1, "маленький" to 1, "маленькая" to 1, "мал" to 1,
    "средний" to 2, "средняя" to 2, "средние" to 2, "сред" to 2,
    "стандартный" to 2, "стандартная" to 2, "станд" to 2,
    "большой" to 3, "большая" to 3, "большие" to 3, "бол" to 3,
    "xl" to 4, "maxx" to 4, "баскет" to 4,
)
private val PotatoOnlySizeRanks = mapOf("двойной" to 4, "двойная" to 4)
private val SizeWordPattern = Regex(
    """(?iu)(?<![\p{L}\p{N}])(""" +
        (SizeRanks.keys + PotatoOnlySizeRanks.keys).joinToString("|") +
        """)\.?(?![\p{L}\p{N}])""",
)
// "0,5 л", "0.8", "1 л": a bare decimal in a menu name is a drink volume too.
private val VolumePattern = Regex(
    """(?iu)(?<![\p{L}\p{N}])(\d+[.,]\d+|\d+(?=\s*л))(?:\s*л(?![\p{L}])\.?)?""",
)
private val PotatoPattern = Regex("""(?iu)картоф|(?<![\p{L}])фри(?![\p{L}])""")

internal fun restaurantTemplateChoices(
    templates: List<Template>,
): List<RestaurantTemplateChoice> {
    val grouped = linkedMapOf<String, MutableList<Template>>()
    val singles = mutableListOf<RestaurantTemplateChoice.Single>()

    templates.forEach { template ->
        val family = restaurantFamily(template)
        if (family == null) {
            singles += RestaurantTemplateChoice.Single(template)
        } else {
            grouped.getOrPut(family.key) { mutableListOf() } += template
        }
    }

    val choices = singles.toMutableList<RestaurantTemplateChoice>()
    grouped.forEach { (key, variants) ->
        if (variants.size == 1) {
            choices += RestaurantTemplateChoice.Single(variants.single())
            return@forEach
        }
        val ordered = variants.sortedWith(
            compareBy<Template> { restaurantQuantity(it.name) ?: Int.MAX_VALUE }
                .thenBy { it.name.length }
                .thenBy { it.name },
        )
        val representative = ordered.minWithOrNull(
            compareBy<Template> { if (normalizedName(it.name) == "воппер") 0 else 1 }
                .thenBy { it.name.length }
                .thenByDescending { it.usageCount },
        ) ?: ordered.first()
        choices += RestaurantTemplateChoice.Variants(
            RestaurantVariantGroup(
                id = "restaurant:$key",
                prefix = representative.prefix.lowercase(),
                name = restaurantFamily(representative)?.displayWordCount?.let { wordCount ->
                    familyName(representative.name).split(' ').take(wordCount).joinToString(" ")
                } ?: familyName(representative.name),
                variants = ordered,
            ),
        )
    }
    return choices.sortedWith(
        compareByDescending<RestaurantTemplateChoice> { choice ->
            when (choice) {
                is RestaurantTemplateChoice.Single -> choice.template.usageCount
                is RestaurantTemplateChoice.Variants -> choice.group.variants.sumOf { it.usageCount }
            }
        }.thenBy { choice ->
            when (choice) {
                is RestaurantTemplateChoice.Single -> choice.template.name
                is RestaurantTemplateChoice.Variants -> choice.group.name
            }
        },
    )
}

internal fun restaurantQuantity(name: String): Int? =
    QuantityPattern.find(name)?.groupValues?.getOrNull(1)?.toIntOrNull()

internal fun variantForQuantity(group: RestaurantVariantGroup, quantity: Int): Template? =
    group.variants.firstOrNull { variant -> restaurantQuantity(variant.name) == quantity }

private data class RestaurantFamily(
    val key: String,
    val displayWordCount: Int? = null,
)

private data class NamedFamilyRule(
    val prefix: String,
    val key: String,
    val displayWordCount: Int,
    val matches: (String) -> Boolean,
)

private val NamedFamilyRules = listOf(
    NamedFamilyRule("rostics", "rostmaster", 1) { name ->
        name == "ростмастер" || name.startsWith("ростмастер ")
    },
    NamedFamilyRule("rostics", "bites", 1) { name ->
        name.startsWith("байтсы из куриного филе")
    },
    NamedFamilyRule("vit", "omelet", 1) { name ->
        name == "омлет" || name.startsWith("омлет с ")
    },
    NamedFamilyRule("vit", "fried-eggs", 1) { name ->
        name == "яичница" || name.startsWith("яичница с ")
    },
    NamedFamilyRule("vit", "egg-muffin", 3) { name ->
        name.startsWith("маффин с яйцом и ")
    },
)

private fun restaurantFamily(template: Template): RestaurantFamily? {
    val prefix = template.prefix.lowercase()
    if (prefix !in RestaurantPrefixes) return null
    val normalized = normalizedName(template.name)
    val quantity = restaurantQuantity(template.name)
    if (quantity != null) {
        val base = normalizedName(QuantityPattern.replace(template.name, " "))
        if (base.isNotBlank()) return RestaurantFamily("$prefix:quantity:$base")
    }
    if (
        prefix == "bk" &&
        StandaloneWhopperPattern.containsMatchIn(normalized) &&
        !normalized.contains(" ролл") &&
        !normalized.startsWith("экстра ")
    ) {
        return RestaurantFamily("bk:named:whopper")
    }
    if (!template.name.contains('+') && restaurantSize(template.name) != null) {
        val base = normalizedName(withoutSize(template.name))
        if (base.isNotBlank()) return RestaurantFamily("$prefix:size:$base")
    }
    NamedFamilyRules.firstOrNull { rule ->
        rule.prefix == prefix && rule.matches(normalized)
    }?.let { rule ->
        return RestaurantFamily(
            key = "$prefix:named:${rule.key}",
            displayWordCount = rule.displayWordCount,
        )
    }
    return null
}

internal fun restaurantSize(name: String): RestaurantSize? {
    val potato = PotatoPattern.containsMatchIn(name)
    val word = SizeWordPattern.findAll(name)
        .map { it.groupValues[1] }
        .lastOrNull { token -> potato || token.lowercase() !in PotatoOnlySizeRanks }
    val liters = VolumePattern.find(name)?.groupValues?.get(1)?.replace(',', '.')?.toDoubleOrNull()
    if (word == null && liters == null) return null
    val key = word?.lowercase()
    val rank = key?.let { SizeRanks[it] ?: PotatoOnlySizeRanks[it] }
    return RestaurantSize(
        word = word?.replaceFirstChar { it.titlecase() },
        rank = rank,
        liters = liters,
    )
}

private fun withoutSize(name: String): String {
    val potato = PotatoPattern.containsMatchIn(name)
    val noVolume = VolumePattern.replace(name, " ")
    return SizeWordPattern.replace(noVolume) { match ->
        if (potato || match.groupValues[1].lowercase() !in PotatoOnlySizeRanks) " " else match.value
    }
}

private fun familyName(name: String): String {
    return QuantityPattern.replace(withoutSize(name), " ")
        .replace(Regex("""\s+"""), " ")
        .trim(' ', '-', '(', ')', ',')
}

private fun normalizedName(name: String): String =
    NonWordPattern.replace(name.lowercase().replace('ё', 'е'), " ").trim()
