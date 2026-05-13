package com.local.glucotracker.ui.navigation

sealed class Route(val route: String) {
    data object Today : Route("today") {
        const val PatternWithDate = "today/{date}"
        const val ArgDate = "date"
        fun forDate(date: kotlinx.datetime.LocalDate): String = "today/$date"
    }
    data object History : Route("history")
    data object Base : Route("base")
    data object More : Route("more")
    data object OutboxInspector : Route("outbox") {
        const val Pattern = "outbox?focus={id}"
        const val DeepLinkUri = "glucotracker://outbox"
        const val ArgId = "id"
        fun focus(id: String): String = "outbox?focus=$id"
    }
    data class Record(val id: String) : Route("record/$id") {
        companion object {
            const val Pattern = "record/{id}"
            const val ArgId = "id"
        }
    }
    data object Capture : Route("capture")
    data object PhotoCapture : Route("photo_capture")
}
