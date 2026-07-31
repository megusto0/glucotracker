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
    NamedFamilyRule("rostics", "fries", 2) { name ->
        name.startsWith("картофель фри ") || name == "картофель фри"
    },
    NamedFamilyRule("rostics", "country-potatoes", 2) { name ->
        name.startsWith("картофель по деревенски")
    },
    NamedFamilyRule("bk", "country-potatoes", 2) { name ->
        name.startsWith("картофель деревенский ")
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

private fun familyName(name: String): String {
    return QuantityPattern.replace(name, " ")
        .replace(Regex("""\s+"""), " ")
        .trim(' ', '-', '(', ')')
}

private fun normalizedName(name: String): String =
    NonWordPattern.replace(name.lowercase().replace('ё', 'е'), " ").trim()
