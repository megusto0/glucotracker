package com.local.glucotracker.ui.navigation

sealed class Route(val route: String) {
    data object Today : Route("today")
    data object Glucose : Route("glucose")
    data object History : Route("history")
    data object Base : Route("base")
    data object More : Route("more")
    data class Record(val id: String) : Route("record/$id") {
        companion object {
            const val Pattern = "record/{id}"
            const val ArgId = "id"
        }
    }
    data object Capture : Route("capture")
    data object PhotoCapture : Route("photo_capture")
    data class Draft(val outboxId: String) : Route("draft/$outboxId") {
        companion object {
            const val Pattern = "draft/{outboxId}"
            const val ArgOutboxId = "outboxId"
        }
    }
    data object TextInput : Route("text_input")
    data object TemplatePicker : Route("template_picker")
}
