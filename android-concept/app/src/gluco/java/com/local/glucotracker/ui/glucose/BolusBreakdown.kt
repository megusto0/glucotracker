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
import androidx.compose.ui.unit.Dp
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
import com.local.glucotracker.generated.model.InsulinRecommendationResponse
import com.local.glucotracker.generated.model.TopUpDoseResponse
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
    val unavailableReason: BolusUnavailableReason? = null,
    val omittedCorrectionReason: BolusCorrectionGap? = null,
    val configuredIcr: Double? = null,
    val icrAfterSleep: Boolean = false,
    val projectionStale: Boolean,
)

internal enum class BolusUnavailableReason {
    Glucose,
    Icr,
    History,
    Carbs,
    LowOrFalling,
}

internal enum class BolusCorrectionGap {
    Glucose,
    Trend,
    Isf,
    Target,
}

@HiltViewModel
class BolusBreakdownViewModel @Inject constructor(
    private val glucoseApi: GlucoseApi,
) : ViewModel() {

    private val _calc = MutableStateFlow<BolusCalcUi?>(null)
    internal val calc: StateFlow<BolusCalcUi?> = _calc.asStateFlow()
    private val _loadFailed = MutableStateFlow(false)
    internal val loadFailed: StateFlow<Boolean> = _loadFailed.asStateFlow()

    fun load(event: InsulinEvent, mealIds: List<String>) {
        _calc.value = null
        _loadFailed.value = false
        viewModelScope.launch {
            val loaded = runCatching {
                if (event.eventType == InsulinEventType.Bolus && mealIds.isNotEmpty()) {
                    glucoseApi.insulinRecommendation(
                        mealIds.distinct().map(java.util.UUID::fromString),
                        calculationAt = event.timestamp,
                    ).toMealBolusCalcUi()
                } else {
                    glucoseApi.topUpDose(
                        at = event.timestamp,
                        excludeInsulinId = runCatching { java.util.UUID.fromString(event.id) }
                            .getOrNull(),
                    ).toBolusCalcUi()
                }
            }.getOrNull()
            if (loaded == null) {
                _loadFailed.value = true
                return@launch
            }
            _calc.value = loaded
        }
    }
}

/** The first food bolus belongs to the meal recommendation, not top-up math. */
internal fun InsulinRecommendationResponse.toMealBolusCalcUi(): BolusCalcUi {
    val mealUnits = recommendedUnits?.toDouble()
    val effectiveIcr = icrGPerUnit?.toDouble()
    val afterSleepIcrIsDirect = icrAfterSleep == true &&
        methodVersion == "historical-episode-median-v3"
    val usableCorrection =
        correctionStatus == InsulinRecommendationResponse.CorrectionStatus.READY ||
            correctionStatus == InsulinRecommendationResponse.CorrectionStatus.NOT_NEEDED ||
            correctionStatus == InsulinRecommendationResponse.CorrectionStatus.LOW_OR_FALLING
    val correctionUnits = correctionUnits?.toDouble().takeIf { usableCorrection }
    val total = totalRecommendedUnits?.toDouble().takeIf { usableCorrection } ?: mealUnits
    return BolusCalcUi(
        state = BolusStateUi(
            glucose = correctionGlucoseMmolL?.toDouble(),
            iob = correctionIobUnits?.toDouble(),
            cob = correctionPriorCobG?.toDouble(),
            icr = effectiveIcr,
            isf = correctionIsfMmolLPerUnit?.toDouble(),
            target = correctionTargetMmolL?.toDouble(),
        ),
        terms = buildList {
            mealUnits?.let {
                add(
                    BolusTermUi(
                        label = "meal",
                        formula = if (afterSleepIcrIsDirect && effectiveIcr != null) {
                            "${grams(targetCarbsG.toDouble())} / ${mmol(effectiveIcr)}"
                        } else {
                            null
                        },
                        value = it,
                    ),
                )
            }
            correctionUnits?.let {
                add(BolusTermUi(label = "correction", formula = null, value = it))
            }
            correctionExcessIobUnits?.toDouble()?.takeIf { it > 0.0 }?.let {
                add(BolusTermUi(label = "free_iob", formula = null, value = -it))
            }
        },
        suggestedUnits = total,
        unavailableNote = null,
        unavailableReason = when (status) {
            InsulinRecommendationResponse.Status.INSUFFICIENT_HISTORY ->
                BolusUnavailableReason.History
            InsulinRecommendationResponse.Status.MEAL_WITHOUT_CARBS ->
                BolusUnavailableReason.Carbs
            InsulinRecommendationResponse.Status.LOW_OR_FALLING ->
                BolusUnavailableReason.LowOrFalling
            InsulinRecommendationResponse.Status.READY -> null
        },
        omittedCorrectionReason = when (correctionStatus) {
            InsulinRecommendationResponse.CorrectionStatus.GLUCOSE_UNAVAILABLE ->
                BolusCorrectionGap.Glucose
            InsulinRecommendationResponse.CorrectionStatus.TREND_UNAVAILABLE ->
                BolusCorrectionGap.Trend
            InsulinRecommendationResponse.CorrectionStatus.ISF_UNAVAILABLE ->
                BolusCorrectionGap.Isf
            InsulinRecommendationResponse.CorrectionStatus.TARGET_REQUIRED ->
                BolusCorrectionGap.Target
            else -> null
        },
        configuredIcr = icrConfiguredGPerUnit?.toDouble(),
        icrAfterSleep = icrAfterSleep == true,
        projectionStale = false,
    )
}

internal fun TopUpDoseResponse.toBolusCalcUi(): BolusCalcUi {
    val glucose = glucoseMmolL?.toDouble()
    val target = targetMmolL?.toDouble()
    val isf = isfMmolLPerUnit?.toDouble()
    val cob = cobG?.toDouble()
    val icr = icrGPerUnit?.toDouble()
    val iob = iobUnits?.toDouble()
    val carb = carbUnits?.toDouble()
    val correction = correctionUnits?.toDouble()

    val terms = buildList {
        if (correction != null && glucose != null && target != null && isf != null) {
            add(
                BolusTermUi(
                    label = "correction",
                    formula = "(${mmol(glucose)}−${mmol(target)}) / ${mmol(isf)}",
                    value = correction,
                ),
            )
        }
        if (carb != null && cob != null && icr != null) {
            add(
                BolusTermUi(
                    label = "carbs",
                    formula = "${grams(cob)} / ${mmol(icr)}",
                    value = carb,
                ),
            )
        }
        if (iob != null) {
            add(BolusTermUi(label = "iob", formula = null, value = -iob))
        }
    }

    val units = units?.toDouble()
    return BolusCalcUi(
        state = BolusStateUi(glucose, iob, cob, icr, isf, target),
        terms = terms,
        suggestedUnits = units,
        unavailableNote = note.takeIf { units == null },
        unavailableReason = when (status) {
            TopUpDoseResponse.Status.GLUCOSE_UNAVAILABLE -> BolusUnavailableReason.Glucose
            TopUpDoseResponse.Status.ICR_UNAVAILABLE -> BolusUnavailableReason.Icr
            else -> null
        },
        // The caveat only explains a calculation that actually exists. When
        // glucose or ICR is absent there is no fallback arithmetic to qualify.
        projectionStale = units != null &&
            projectionSource == TopUpDoseResponse.ProjectionSource.NONE,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BolusBreakdownSheet(
    events: List<InsulinEvent>,
    mealAt: Instant?,
    mealIds: List<String>,
    onDismiss: () -> Unit,
) {
    val ordered = remember(events) { events.sortedBy { it.timestamp } }
    if (ordered.isEmpty()) return
    var selected by remember(ordered.map { it.id }) { mutableIntStateOf(ordered.lastIndex) }
    val viewModel: BolusBreakdownViewModel = hiltViewModel()
    LaunchedEffect(ordered[selected].id, mealIds) {
        viewModel.load(ordered[selected], mealIds)
    }
    val calc by viewModel.calc.collectAsStateWithLifecycle()
    val loadFailed by viewModel.loadFailed.collectAsStateWithLifecycle()

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
            loadFailed = loadFailed,
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
    loadFailed: Boolean = false,
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
            if (loadFailed) {
                Text(
                    text = stringResource(R.string.bolus_calc_load_error),
                    modifier = Modifier.padding(horizontal = 20.dp).padding(top = 12.dp),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                )
            } else {
                Spacer(Modifier.height(90.dp))
            }
            return@Column
        }

        val hasCalculationContext = calc.state.glucose != null ||
            calc.terms.isNotEmpty() ||
            calc.suggestedUnits != null
        if (hasCalculationContext) {
            BolusCalculationBlock(
                state = calc.state,
                terms = calc.terms,
                total = calc.suggestedUnits,
                at = clock(chosen.timestamp, zone),
            )
        }

        val unavailableDetail = calc.unavailableNote ?: when (calc.unavailableReason) {
            BolusUnavailableReason.Glucose -> stringResource(R.string.bolus_calc_missing_glucose)
            BolusUnavailableReason.Icr -> stringResource(R.string.bolus_calc_missing_icr)
            BolusUnavailableReason.History -> stringResource(R.string.bolus_calc_missing_history)
            BolusUnavailableReason.Carbs -> stringResource(R.string.bolus_calc_missing_carbs)
            BolusUnavailableReason.LowOrFalling ->
                stringResource(R.string.bolus_calc_low_or_falling)
            null -> null
        }
        unavailableDetail?.let { note ->
            Text(
                text = stringResource(R.string.bolus_calc_unavailable, note),
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 10.dp),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        }

        calc.omittedCorrectionReason?.let { gap ->
            Text(
                text = stringResource(
                    when (gap) {
                        BolusCorrectionGap.Glucose -> R.string.bolus_correction_gap_glucose
                        BolusCorrectionGap.Trend -> R.string.bolus_correction_gap_trend
                        BolusCorrectionGap.Isf -> R.string.bolus_correction_gap_isf
                        BolusCorrectionGap.Target -> R.string.bolus_correction_gap_target
                    },
                ),
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 8.dp),
                color = GT.colors.warn,
                style = GT.type.sansLabel,
            )
        }

        if (calc.icrAfterSleep && calc.configuredIcr != null && calc.state.icr != null) {
            Text(
                text = stringResource(
                    R.string.bolus_first_after_sleep_icr,
                    mmol(calc.configuredIcr),
                    mmol(calc.state.icr),
                ),
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 8.dp),
                color = GT.colors.ink2,
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

/** Shared calculation body for a recommendation and a recorded bolus review. */
@Composable
internal fun BolusCalculationBlock(
    state: BolusStateUi,
    terms: List<BolusTermUi>,
    total: Double?,
    at: String,
    modifier: Modifier = Modifier,
    horizontalPadding: Dp = 20.dp,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        BolusStateBlock(
            state = state,
            at = at,
            horizontalPadding = horizontalPadding,
        )
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = horizontalPadding)
                .padding(top = 12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            terms.forEach { term -> TermRow(term) }
            total?.let {
                GTHairlineDivider()
                TermRow(
                    BolusTermUi(
                        label = "total",
                        formula = null,
                        value = it,
                        isTotal = true,
                    ),
                )
            }
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
private fun BolusStateBlock(state: BolusStateUi, at: String, horizontalPadding: Dp) {
    Text(
        text = stringResource(R.string.bolus_state_at, at),
        modifier = Modifier
            .padding(horizontal = horizontalPadding)
            .padding(top = 14.dp, bottom = 5.dp),
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
        modifier = Modifier.fillMaxWidth().padding(horizontal = horizontalPadding),
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
                    "meal" -> R.string.insulin_term_meal
                    "iob" -> R.string.bolus_term_iob
                    "free_iob" -> R.string.bolus_term_free_iob
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
