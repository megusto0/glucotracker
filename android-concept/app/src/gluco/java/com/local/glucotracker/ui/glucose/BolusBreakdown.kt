package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.domain.model.InsulinEvent
import com.local.glucotracker.domain.model.InsulinEventType
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

/**
 * Why one bolus was the size it was — mockup screen G.
 *
 * The pre-meal calculator answers "how much now". This answers "why that much",
 * and they are different products that had been sharing one card: the same
 * widget carried a dose to enter *and* a verdict on a dose already given. The
 * two are split here, and this is the retrospective half.
 *
 * Every number comes from the backend recomputed at the bolus's own timestamp.
 * Nothing is re-derived on the client, because a second opinion that disagreed
 * with the diary row that opened this sheet would be worse than no sheet.
 */
internal data class BolusStateUi(
    val glucose: Double?,
    val iob: Double?,
    val cob: Double?,
    val icr: Double?,
    val isf: Double?,
    val target: Double?,
)

internal data class BolusTermUi(
    val label: String,
    val formula: String?,
    val value: Double,
    val isTotal: Boolean = false,
)

internal data class BolusCalcUi(
    val state: BolusStateUi,
    val terms: List<BolusTermUi>,
    val suggestedUnits: Double?,
    val unavailableNote: String?,
    val projectionStale: Boolean,
)

@HiltViewModel
class BolusBreakdownViewModel @Inject constructor(
    private val glucoseApi: GlucoseApi,
) : ViewModel() {

    private val _calc = MutableStateFlow<BolusCalcUi?>(null)
    internal val calc: StateFlow<BolusCalcUi?> = _calc.asStateFlow()

    fun load(at: Instant, insulinId: String) {
        _calc.value = null
        viewModelScope.launch {
            val response = runCatching {
                glucoseApi.topUpDose(
                    at = at,
                    excludeInsulinId = runCatching { java.util.UUID.fromString(insulinId) }
                        .getOrNull(),
                )
            }.getOrNull()
            if (response == null) {
                _calc.value = null
                return@launch
            }
            val glucose = response.glucoseMmolL?.toDouble()
            val target = response.targetMmolL?.toDouble()
            val isf = response.isfMmolLPerUnit?.toDouble()
            val cob = response.cobG?.toDouble()
            val icr = response.icrGPerUnit?.toDouble()
            val iob = response.iobUnits?.toDouble()
            val carbUnits = response.carbUnits?.toDouble()
            val correctionUnits = response.correctionUnits?.toDouble()

            val terms = buildList {
                if (correctionUnits != null && glucose != null && target != null && isf != null) {
                    add(
                        BolusTermUi(
                            label = "correction",
                            formula = "(${mmol(glucose)}−${mmol(target)}) / ${mmol(isf)}",
                            value = correctionUnits,
                        ),
                    )
                }
                if (carbUnits != null && cob != null && icr != null) {
                    add(
                        BolusTermUi(
                            label = "carbs",
                            formula = "${grams(cob)} / ${mmol(icr)}",
                            value = carbUnits,
                        ),
                    )
                }
                if (iob != null) {
                    add(BolusTermUi(label = "iob", formula = null, value = -iob))
                }
            }

            _calc.value = BolusCalcUi(
                state = BolusStateUi(glucose, iob, cob, icr, isf, target),
                terms = terms,
                suggestedUnits = response.units?.toDouble(),
                unavailableNote = response.note.takeIf { response.units == null },
                // The stored forecast for a past minute has usually aged out, so
                // the correction term runs from the reading rather than from
                // where it was heading. The sheet says so instead of implying
                // this reproduces what was on screen at the time.
                projectionStale = response.projectionSource?.value == "none",
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BolusBreakdownSheet(
    events: List<InsulinEvent>,
    mealAt: Instant?,
    onDismiss: () -> Unit,
) {
    val ordered = remember(events) { events.sortedBy { it.timestamp } }
    if (ordered.isEmpty()) return
    var selected by remember(ordered.map { it.id }) { mutableIntStateOf(ordered.lastIndex) }
    val viewModel: BolusBreakdownViewModel = hiltViewModel()
    LaunchedEffect(ordered[selected].id) {
        viewModel.load(ordered[selected].timestamp, ordered[selected].id)
    }
    val calc by viewModel.calc.collectAsStateWithLifecycle()

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = GT.colors.surface,
    ) {
        BolusBreakdownContent(
            doses = ordered,
            mealAt = mealAt,
            selectedIndex = selected,
            calc = calc,
            onSelect = { selected = it },
        )
    }
}

/**
 * The sheet without its loading, so a golden can render it.
 *
 * The snapshot suite draws a fake for every glucose surface, so anything that
 * only exists inside its own loader is invisible to a diff.
 */
@Composable
internal fun BolusBreakdownContent(
    doses: List<InsulinEvent>,
    mealAt: Instant?,
    selectedIndex: Int,
    calc: BolusCalcUi?,
    onSelect: (Int) -> Unit,
) {
    val zone = TimeZone.currentSystemDefault()
    val chosen = doses[selectedIndex]
    val total = doses.sumOf { it.doseUnits }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface)
            .padding(bottom = 24.dp),
    ) {
        Text(
            text = stringResource(R.string.bolus_breakdown_doses, units(total)),
            modifier = Modifier.padding(horizontal = 20.dp).padding(bottom = 6.dp),
            color = GT.colors.muted,
            style = GT.type.kicker,
        )
        // Every dose of the sitting, each saying what it was for. Stepping
        // between them is the point: a chasing bolus only means anything next
        // to the one it was chasing.
        doses.forEachIndexed { index, event ->
            DoseRow(
                event = event,
                mealAt = mealAt,
                zone = zone,
                selected = index == selectedIndex,
                onClick = { onSelect(index) },
            )
        }

        GTHairlineDivider(modifier = Modifier.padding(horizontal = 20.dp))

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(top = 12.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                text = stringResource(
                    R.string.bolus_breakdown_of,
                    selectedIndex + 1,
                    doses.size,
                ) + " · " + clock(chosen.timestamp, zone),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            Text(
                text = stringResource(R.string.bolus_entered, units(chosen.doseUnits)) +
                    (
                        calc?.suggestedUnits
                            ?.let { " · " + stringResource(R.string.bolus_calc_was, units(it)) }
                            ?: ""
                        ),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
        }

        if (calc == null) {
            Spacer(Modifier.height(90.dp))
            return@Column
        }

        BolusStateBlock(state = calc.state, at = clock(chosen.timestamp, zone))

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(top = 12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            calc.terms.forEach { term -> TermRow(term) }
            calc.suggestedUnits?.let { total ->
                GTHairlineDivider()
                TermRow(
                    BolusTermUi(
                        label = "total",
                        formula = null,
                        value = total,
                        isTotal = true,
                    ),
                )
            }
        }

        calc.unavailableNote?.let { note ->
            Text(
                text = stringResource(R.string.bolus_calc_unavailable, note),
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 10.dp),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        }

        calc.suggestedUnits?.let { suggested ->
            val delta = chosen.doseUnits - suggested
            Text(
                text = when {
                    abs(delta) < 0.05 -> stringResource(R.string.bolus_delta_equal)
                    delta > 0 -> stringResource(R.string.bolus_delta_over, units(delta))
                    else -> stringResource(R.string.bolus_delta_under, units(-delta))
                },
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 12.dp),
                color = GT.colors.ink2,
                style = GT.type.sansLabel,
            )
        }

        if (calc.projectionStale) {
            Text(
                text = stringResource(R.string.bolus_caveats),
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 8.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
            )
        }
    }
}

@Composable
private fun DoseRow(
    event: InsulinEvent,
    mealAt: Instant?,
    zone: TimeZone,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 44.dp)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = units(event.doseUnits),
            color = if (selected) GT.colors.ink else GT.colors.ink2,
            style = GT.type.monoNumber,
            maxLines = 1,
        )
        Spacer(Modifier.width(12.dp))
        Text(
            text = bolusReason(event, mealAt),
            modifier = Modifier.weight(1f),
            color = if (selected) GT.colors.ink2 else GT.colors.muted,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = clock(event.timestamp, zone),
            color = GT.colors.muted,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun BolusStateBlock(state: BolusStateUi, at: String) {
    Text(
        text = stringResource(R.string.bolus_state_at, at),
        modifier = Modifier.padding(horizontal = 20.dp).padding(top = 14.dp, bottom = 5.dp),
        color = GT.colors.muted,
        style = GT.type.kicker,
    )
    val cells = listOfNotNull(
        state.glucose?.let { stringResource(R.string.bolus_state_glucose) to mmol(it) },
        state.iob?.let { stringResource(R.string.bolus_state_iob) to units(it) },
        state.cob?.let { stringResource(R.string.bolus_state_cob) to grams(it) },
        state.icr?.let { stringResource(R.string.bolus_state_icr) to mmol(it) },
        state.isf?.let { stringResource(R.string.bolus_state_isf) to mmol(it) },
        state.target?.let { stringResource(R.string.bolus_state_target) to mmol(it) },
    )
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        cells.forEach { (label, value) ->
            Column(horizontalAlignment = Alignment.Start) {
                Text(
                    text = label,
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 9.sp),
                    maxLines = 1,
                )
                Text(
                    text = value,
                    color = GT.colors.ink,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun TermRow(term: BolusTermUi) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            text = stringResource(
                when (term.label) {
                    "correction" -> R.string.bolus_term_correction
                    "carbs" -> R.string.bolus_term_carbs
                    "iob" -> R.string.bolus_term_iob
                    else -> R.string.bolus_term_total
                },
            ),
            color = if (term.isTotal) GT.colors.ink else GT.colors.ink2,
            style = GT.type.sansLabel,
            maxLines = 1,
        )
        // The formula next to its own result, so the line can be checked rather
        // than believed. One cramped row of interleaved labels and signs is what
        // this replaces.
        term.formula?.let { formula ->
            Spacer(Modifier.width(6.dp))
            Text(
                text = formula,
                modifier = Modifier.weight(1f),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        } ?: Spacer(Modifier.weight(1f))
        Text(
            text = signedUnits(term.value),
            color = if (term.isTotal) GT.colors.ink else GT.colors.ink2,
            style = if (term.isTotal) GT.type.monoNumber else GT.type.monoLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun bolusReason(event: InsulinEvent, mealAt: Instant?): String {
    if (event.eventType == InsulinEventType.CatchUp) {
        return stringResource(R.string.bolus_reason_catch_up)
    }
    if (event.eventType == InsulinEventType.Correction) {
        return stringResource(R.string.bolus_reason_correction)
    }
    if (mealAt == null) return stringResource(R.string.bolus_reason_alone)
    val minutes = ((event.timestamp - mealAt).inWholeSeconds / 60.0).roundToInt()
    return when {
        abs(minutes) <= 10 -> stringResource(R.string.bolus_reason_with_meal)
        minutes < 0 -> stringResource(R.string.bolus_reason_before, -minutes)
        else -> stringResource(R.string.bolus_reason_after, minutes)
    }
}

private fun clock(at: Instant, zone: TimeZone): String {
    val time = at.toLocalDateTime(zone).time
    return "%02d:%02d".format(time.hour, time.minute)
}

private fun mmol(value: Double): String = "%.1f".format(value).replace('.', ',')

private fun grams(value: Double): String = "${value.roundToInt()} г"

private fun units(value: Double): String = "%.1f".format(value).replace('.', ',')

private fun signedUnits(value: Double): String {
    val body = units(abs(value))
    return if (value < 0) "−$body" else body
}
