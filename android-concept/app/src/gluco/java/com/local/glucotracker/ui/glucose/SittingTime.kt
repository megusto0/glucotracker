package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.MealPatchPayload
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.LocalTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant
import kotlinx.datetime.toLocalDateTime

/** One dish of a sitting, as far as moving its time is concerned. */
data class SittingMeal(val id: String, val eatenAt: Instant)

@HiltViewModel
class SittingTimeViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
) : ViewModel() {

    /**
     * Move a whole sitting, keeping the dishes in the order they were eaten.
     *
     * Every plate shifts by the same amount rather than collapsing onto one
     * instant: the spacing inside a sitting is real, and the backend reads it
     * — grouping, absorption and the catch-up test all measure from the first
     * plate. Correcting a sitting logged an hour late should not also claim
     * everything was eaten simultaneously.
     */
    fun shiftSitting(meals: List<SittingMeal>, newStart: Instant) {
        val first = meals.minByOrNull { it.eatenAt } ?: return
        val delta = newStart - first.eatenAt
        if (delta.inWholeSeconds == 0L) return
        viewModelScope.launch {
            meals.sortedBy { it.eatenAt }.forEach { meal ->
                outboxRepository.enqueue(
                    OutboxKind.EditMeal(
                        serverId = meal.id,
                        patch = MealPatchPayload(eatenAt = meal.eatenAt + delta),
                    ),
                )
            }
        }
    }
}

/**
 * Move the time of a whole sitting in one go.
 *
 * Editing plate by plate was the only way to correct a sitting logged at the
 * wrong hour, and every intermediate save was a sitting split across two
 * times — which the backend regroups on, so the cards reshuffled underfoot.
 * Offered only when every dish has reached the server: a queued record has no
 * id to patch, and shifting half a sitting is worse than shifting none.
 *
 * A sitting of one plate is still a sitting, and its time is just as likely to
 * be wrong, so it is offered there too rather than sending the user off to the
 * card stack for the same edit.
 */
@Composable
fun SittingTimeButton(meals: List<SittingMeal>, modifier: Modifier = Modifier) {
    if (meals.isEmpty()) return
    var sheetOpen by remember { mutableStateOf(false) }
    GlucoCardAction(
        text = stringResource(R.string.sitting_time_action),
        onClick = { sheetOpen = true },
        modifier = modifier,
    )
    if (sheetOpen) {
        SittingTimeSheet(meals = meals, onDismiss = { sheetOpen = false })
    }
}

/**
 * Hours and minutes as two boxes with the colon printed between them.
 *
 * This was one field pre-filled with "13:41" over a numeric keypad that has no
 * colon key, so the format it was asking for could not be typed at all. Two
 * boxes of two digits need neither punctuation nor an explanation. The line
 * underneath names the move being made, because "сдвинуть" is the operation
 * and a destination time alone does not show it.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SittingTimeSheet(meals: List<SittingMeal>, onDismiss: () -> Unit) {
    val viewModel: SittingTimeViewModel = hiltViewModel()
    val zone = TimeZone.currentSystemDefault()
    val start = meals.minOf { it.eatenAt }
    val startLocal = start.toLocalDateTime(zone)
    var hours by remember(start) { mutableStateOf("%02d".format(startLocal.time.hour)) }
    var minutes by remember(start) { mutableStateOf("%02d".format(startLocal.time.minute)) }
    val minuteFocus = remember { FocusRequester() }
    val target = remember(start, hours, minutes) {
        sittingStart(start, hours, minutes, zone)
    }
    val shiftMinutes = target?.let { (it - start).inWholeMinutes } ?: 0L
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = GT.colors.surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .imePadding()
                .padding(horizontal = 18.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.sitting_time_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            Text(
                text = if (meals.size == 1) {
                    stringResource(R.string.sitting_time_hint_single)
                } else {
                    stringResource(R.string.sitting_time_hint, meals.size)
                },
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                ClockField(
                    value = hours,
                    placeholder = stringResource(R.string.sitting_time_hours),
                    onValueChange = { next ->
                        hours = next
                        if (next.length == 2) minuteFocus.requestFocus()
                    },
                )
                Text(text = ":", color = GT.colors.ink, style = GT.type.monoNumber)
                ClockField(
                    value = minutes,
                    placeholder = stringResource(R.string.sitting_time_minutes),
                    onValueChange = { minutes = it },
                    focusRequester = minuteFocus,
                )
                Spacer(Modifier.width(4.dp))
                GTOutlineButton(
                    text = stringResource(R.string.sitting_time_save),
                    enabled = target != null && shiftMinutes != 0L,
                    onClick = {
                        if (target != null && shiftMinutes != 0L) {
                            viewModel.shiftSitting(meals, target)
                            onDismiss()
                        }
                    },
                )
            }
            Text(
                text = if (target == null) {
                    stringResource(R.string.sitting_time_unchanged)
                } else {
                    stringResource(
                        R.string.sitting_time_preview,
                        formatClock(startLocal.time),
                        formatClock(target.toLocalDateTime(zone).time),
                        shiftLabel(shiftMinutes),
                    )
                },
                color = GT.colors.muted,
                style = GT.type.monoLabel,
            )
        }
    }
}

@Composable
private fun ClockField(
    value: String,
    placeholder: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    focusRequester: FocusRequester? = null,
) {
    BasicTextField(
        value = value,
        onValueChange = { next -> onValueChange(next.filter(Char::isDigit).take(2)) },
        modifier = modifier
            .width(58.dp)
            .height(48.dp)
            .then(focusRequester?.let { Modifier.focusRequester(it) } ?: Modifier)
            .background(GT.colors.surface2, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.card),
        textStyle = GT.type.monoNumber.copy(
            color = GT.colors.ink,
            textAlign = TextAlign.Center,
        ),
        cursorBrush = SolidColor(GT.colors.ink),
        singleLine = true,
        keyboardOptions = KeyboardOptions(
            keyboardType = KeyboardType.Number,
            imeAction = ImeAction.Done,
        ),
        decorationBox = { inner ->
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                if (value.isEmpty()) {
                    Text(
                        text = placeholder,
                        color = GT.colors.muted,
                        style = GT.type.monoNumber,
                    )
                }
                inner()
            }
        },
    )
}

private fun formatClock(time: LocalTime): String =
    "%02d:%02d".format(time.hour, time.minute)

@Composable
private fun shiftLabel(minutes: Long): String {
    if (minutes == 0L) return stringResource(R.string.sitting_time_unchanged)
    val sign = if (minutes > 0) "+" else "−"
    val total = kotlin.math.abs(minutes)
    return if (total >= 60) {
        stringResource(R.string.sitting_time_shift_hours, sign, total / 60, total % 60)
    } else {
        stringResource(R.string.sitting_time_shift_minutes, sign, total)
    }
}

/** Two digit strings on the sitting's own day; anything invalid means no move. */
internal fun sittingStart(
    start: Instant,
    hours: String,
    minutes: String,
    zone: TimeZone,
): Instant? {
    val hour = hours.toIntOrNull() ?: return null
    val minute = minutes.toIntOrNull() ?: return null
    if (hour !in 0..23 || minute !in 0..59) return null
    val day = start.toLocalDateTime(zone).date
    return LocalDateTime(day, LocalTime(hour, minute)).toInstant(zone)
}

/**
 * The sitting's own line: a dot for its kind, its time, what it was, its totals.
 *
 * Every group carries one, including a sitting of a single dish. A card that
 * announced itself only when it held two or more made the commonest entry —
 * one plate — the odd one out, and left it with nowhere to put the time.
 *
 * The time is the control. It reads as editable (dashed, with a pencil) and
 * opens the shift sheet on tap, which retires a whole «ВРЕМЯ ПРИЁМА» button
 * from the footer: the thing being changed is right there to be pressed.
 */
@Composable
fun SittingHeader(
    time: String,
    kindLabel: String,
    kindColor: Color,
    totals: String,
    meals: List<SittingMeal>,
    modifier: Modifier = Modifier,
    // What this sitting is, on the server's terms, and the day it was listed
    // on. Both are needed to fetch its breakdown; null leaves the kind label
    // as plain text, which is what a queued record gets.
    episodeKey: String? = null,
    date: LocalDate? = null,
) {
    var sheetOpen by remember { mutableStateOf(false) }
    var breakdownOpen by remember(episodeKey) { mutableStateOf(false) }
    val editable = meals.isNotEmpty()
    val explainable = episodeKey != null && date != null
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp)
            .padding(top = 9.dp, bottom = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(modifier = Modifier.size(7.dp).background(kindColor, GT.shapes.tag))
        Spacer(Modifier.width(9.dp))
        Text(
            text = if (editable) {
                stringResource(R.string.sitting_header_time_editable, time)
            } else {
                time
            },
            modifier = Modifier
                .then(
                    if (editable) {
                        Modifier.clickable(role = Role.Button) { sheetOpen = true }
                    } else {
                        Modifier
                    },
                )
                .then(if (editable) Modifier.dashedUnderline(GT.colors.muted) else Modifier),
            color = GT.colors.ink2,
            style = GT.type.kicker,
            maxLines = 1,
        )
        Spacer(Modifier.width(7.dp))
        // The kind is the other control on this line. The time answers "when
        // was this", the kind answers "what was this" — and the second question
        // is the one with a whole sheet behind it.
        Text(
            text = kindLabel,
            modifier = Modifier
                .weight(1f)
                .then(
                    if (explainable) {
                        Modifier.clickable(role = Role.Button) { breakdownOpen = true }
                    } else {
                        Modifier
                    },
                ),
            color = if (explainable) kindColor else GT.colors.ink2,
            style = GT.type.kicker,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = totals,
            color = GT.colors.muted,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
    if (sheetOpen) {
        SittingTimeSheet(meals = meals, onDismiss = { sheetOpen = false })
    }
    if (breakdownOpen && episodeKey != null && date != null) {
        EpisodeBreakdownSheet(
            episodeKey = episodeKey,
            date = date,
            onDismiss = { breakdownOpen = false },
        )
    }
}

/** A dashed rule under a value that can be changed by pressing it. */
private fun Modifier.dashedUnderline(color: Color): Modifier = drawBehind {
    val y = size.height + 2.dp.toPx()
    drawLine(
        color = color,
        start = Offset(0f, y),
        end = Offset(size.width, y),
        strokeWidth = 1.dp.toPx(),
        pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 2.dp.toPx())),
    )
}
