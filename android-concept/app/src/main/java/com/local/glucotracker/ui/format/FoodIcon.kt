package com.local.glucotracker.ui.format

/**
 * A stand-in picture for food that has no photograph.
 *
 * A second copy of the fridge's `services/icons.py`, deliberately. The fridge
 * owns the rule for the food it stocks and answers with an `icon` on every
 * product, and that answer is always preferred — see [foodIcon]. But a diary
 * entry is not stock: «Бутерброд с сыром и маслом» eaten on Monday is
 * GlucoTracker's own noun, one the fridge has never heard of and should not be
 * asked about. Deriving it here is what lets the same sandwich look the same
 * in search, on Today and in the history, without a round trip for a picture.
 *
 * Keep the two in step. If they ever disagree about a product the server's
 * answer wins, so the visible cost of drift is limited to meals.
 */
private val Rules: List<Pair<Regex, String>> = listOf(
    // Dishes before their ingredients: «Бутерброд с сыром» is a sandwich, and
    // «Овсяная каша на молоке» is porridge, whatever else the name mentions.
    "сметанник" to "🍰",
    "сэндвич|бутерброд" to "🥪",
    "тако|буррито|шаурм" to "🌯",
    "каша" to "🍲",
    "пончик|круассан|бурэкас|треугольник|выпечк|коржи|слойк|булоч" to "🥐",
    "сырок" to "🧁",
    "творог" to "🥣",
    "сыр" to "🧀",
    "йогурт" to "🍧",
    "сливк|молок|кефир" to "🥛",
    "сметан" to "🥣",
    "шницель|куриц|индейк|азу|мяс|филе|цыпл" to "🍗",
    "чечевиц" to "🥣",
    "гречк|крупа" to "🍲",
    "томат|помидор" to "🍅",
    "брокколи" to "🥦",
    "капуст" to "🥬",
    "овощ|смесь" to "🥗",
    "лук" to "🧅",
    "яйц" to "🥚",
    "яблок" to "🍎",
    "лимон" to "🍋",
    "мандарин|апельсин" to "🍊",
    "ежевик|голубик|ягод|клубник|малин" to "🫐",
    "морожен" to "🍦",
    "лепешк|лепёшк|блин|лаваш|батон|хлеб" to "🥞",
    "чак-чак|козинак|халва" to "🍯",
    "сухарик" to "🥨",
    "шоколад|twix|батончик|конфет|драже|skittles|m&m|карамель" to "🍫",
    "френч-дог|сосиск" to "🌭",
    "картофел|фри" to "🍟",
    "бургер|воппер|чизбургер|биг" to "🍔",
    "наггетс|стрипс|крылышк" to "🍗",
    "чай|greenfield|curtis" to "🫖",
    "кола|напит|сок|вода" to "🥤",
    "сахар" to "🧂",
    "масло" to "🫒",
    "майонез" to "🍶",
    "жвачк|mentos|pure fresh" to "🍬",
    "протеин|casein|bombbar" to "💪",
    "арахис|орех|фундук|миндал" to "🥜",
    "гриб|енок|шампиньон|вешенк" to "🍄",
).map { (pattern, icon) -> Regex(pattern, RegexOption.IGNORE_CASE) to icon }

/** Nothing matched. A parcel is honest: something is in there, unnamed. */
const val FallbackFoodIcon = "📦"

/**
 * The emoji that stands for this food, from whatever names describe it.
 *
 * [supplied] is the server's answer where there is one — for stock the fridge
 * has already decided, and its decision outranks anything worked out here.
 */
fun foodIcon(vararg names: String?, supplied: String? = null): String {
    supplied?.takeIf { it.isNotBlank() }?.let { return it }
    val haystack = names.filterNotNull().joinToString(" ")
    if (haystack.isBlank()) return FallbackFoodIcon
    return Rules.firstOrNull { (pattern, _) -> pattern.containsMatchIn(haystack) }
        ?.second
        ?: FallbackFoodIcon
}
