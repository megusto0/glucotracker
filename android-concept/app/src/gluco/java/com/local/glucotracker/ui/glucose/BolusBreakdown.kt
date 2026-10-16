package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.background
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.runtime.mutableStateOf
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.horizontalScroll
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
import com.local.glucotracker.ui.feature.insulin.InsulinManagementSheet
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
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
    /** Meal calculations read carbohydrate from *earlier* meals only. */
    val cobIsPrior: Boolean = false,
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
    /** Set when a follow-up came from the history model, below the balance. */
    val modelBalanceUnits: Double? = null,
)

/** What the lower half of the sheet explains: the meal's doses, or one top-up. */
internal sealed interface BolusSelection {
    data object Meal : BolusSelection
    data class Dose(val index: Int) : BolusSelection
}

/** Doses given for the food: boluses up to an hour after the meal. */
internal fun mealDoseIndices(doses: List<InsulinEvent>, mealAt: Instant?): Set<Int> {
    if (mealAt == null) return emptySet()
    val cutoff = mealAt + MEAL_DOSE_WINDOW
    return doses.indices.filter { index ->
        val dose = doses[index]
        dose.eventType == InsulinEventType.Bolus && dose.timestamp <= cutoff
    }.toSet()
}

internal fun defaultBolusSelection(
    doses: List<InsulinEvent>,
    mealAt: Instant?,
    hasMeal: Boolean,
): BolusSelection =
    if (hasMeal && mealDoseIndices(doses, mealAt).isNotEmpty()) {
        BolusSelection.Meal
    } else {
        BolusSelection.Dose(doses.lastIndex)
    }

private val MEAL_DOSE_WINDOW = kotlin.time.Duration.parse("60m")

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

    /**
     * [forMeal] asks for the meal calculation at [event] — the first dose of the
     * series — and anything else asks what "Сколько добавить?" said then.
     */
    fun load(event: InsulinEvent, mealIds: List<String>, forMeal: Boolean) {
        _calc.value = null
        _loadFailed.value = false
        viewModelScope.launch {
            val loaded = runCatching {
                if (forMeal && mealIds.isNotEmpty()) {
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
            cobIsPrior = true,
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

    // When the history model is the smaller of the two, the balance terms do
    // not add up to the answer, so they are not listed as if they did.
    val fromModel = limitedBy == TopUpDoseResponse.LimitedBy.MODEL
    val terms = if (fromModel) emptyList() else buildList {
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
        modelBalanceUnits = balanceUnits?.toDouble()?.takeIf { fromModel },
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
    var selection by remember(ordered.map { it.id }, mealAt) {
        mutableStateOf(defaultBolusSelection(ordered, mealAt, hasMeal = mealIds.isNotEmpty()))
    }
    val viewModel: BolusBreakdownViewModel = hiltViewModel()
    LaunchedEffect(selection, mealIds) {
        when (val chosen = selection) {
            BolusSelection.Meal -> {
                val first = mealDoseIndices(ordered, mealAt).min()
                viewModel.load(ordered[first], mealIds, forMeal = true)
            }
            is BolusSelection.Dose -> viewModel.load(ordered[chosen.index], mealIds, forMeal = false)
        }
    }
    val calc by viewModel.calc.collectAsStateWithLifecycle()
    val loadFailed by viewModel.loadFailed.collectAsStateWithLifecycle()
    var managed by remember { mutableStateOf<InsulinEvent?>(null) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = GT.colors.surface,
    ) {
        BolusBreakdownContent(
            doses = ordered,
            mealAt = mealAt,
            selection = selection,
            calc = calc,
            loadFailed = loadFailed,
            onSelect = { selection = it },
            onManage = { managed = it },
        )
    }
    managed?.let { event ->
        InsulinManagementSheet(event = event, onDismiss = { managed = null })
    }
}

/**
 * The sheet without its loading, so a golden can render it.
 *
 * The doses of one sitting are a series, not separate decisions: the meal's
 * share was split across several entries and is judged once, against the
 * calculation at the first of them. Comparing a single split entry with the
 * whole meal's calculation produced "you entered −7,9" for a dose that was a
 * third of the plan. A follow-up after the meal is its own decision and is
 * judged against what "Сколько добавить?" said at that moment.
 */
@Composable
internal fun BolusBreakdownContent(
    doses: List<InsulinEvent>,
    mealAt: Instant?,
    selection: BolusSelection,
    calc: BolusCalcUi?,
    loadFailed: Boolean = false,
    onSelect: (BolusSelection) -> Unit,
    onManage: (InsulinEvent) -> Unit = {},
) {
    val zone = TimeZone.currentSystemDefault()
    val mealDoses = remember(doses, mealAt) { mealDoseIndices(doses, mealAt) }
    val total = doses.sumOf { it.doseUnits }
    val anchor = when (selection) {
        BolusSelection.Meal -> doses[mealDoses.min()]
        is BolusSelection.Dose -> doses[selection.index]
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface)
            .padding(bottom = 24.dp),
    ) {
        Text(
            text = stringResource(R.string.bolus_breakdown_doses, units(total)),
            modifier = Modifier.padding(horizontal = 20.dp).padding(bottom = 4.dp),
            color = GT.colors.muted,
            style = GT.type.kicker,
        )
        DoseTimeline(
            doses = doses,
            mealAt = mealAt,
            zone = zone,
            mealDoses = mealDoses,
            selection = selection,
            onSelect = onSelect,
        )

        // A dose entered by mistake is fixed from here too. Only Glucotracker's
        // own entries are offered; Nightscout imports stay read-only.
        val selectedDoses = when (selection) {
            BolusSelection.Meal -> mealDoses.sorted().map { doses[it] }
            is BolusSelection.Dose -> listOf(anchor)
        }.filter { !it.isReadOnly && !it.isPending }
        if (selectedDoses.isNotEmpty()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp)
                    .padding(bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = stringResource(R.string.bolus_edit_doses),
                    color = GT.colors.muted,
                    style = GT.type.kicker,
                )
                selectedDoses.forEach { dose ->
                    GTOutlineButton(
                        text = stringResource(R.string.topup_units, units(dose.doseUnits)),
                        onClick = { onManage(dose) },
                    )
                }
            }
        }

        GTHairlineDivider(modifier = Modifier.padding(horizontal = 20.dp))

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
                at = clock(anchor.timestamp, zone),
            )
        }

        calc.modelBalanceUnits?.let { balance ->
            Text(
                text = stringResource(R.string.bolus_topup_model, units(balance)),
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 6.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel.copy(fontSize = 10.sp),
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

        // One neutral line: what went in against what was calculated. The
        // difference is left to the reader rather than worded as a verdict.
        calc.suggestedUnits?.let { suggested ->
            val given = when (selection) {
                BolusSelection.Meal -> mealDoses.sumOf { doses[it].doseUnits }
                is BolusSelection.Dose -> anchor.doseUnits
            }
            Text(
                text = when (selection) {
                    BolusSelection.Meal ->
                        stringResource(R.string.bolus_meal_given_of, units(given), units(suggested))
                    is BolusSelection.Dose ->
                        stringResource(R.string.bolus_topup_given, units(given), units(suggested))
                },
                modifier = Modifier.padding(horizontal = 20.dp).padding(top = 12.dp),
                color = GT.colors.ink,
                style = GT.type.monoLabel,
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

/**
 * The sitting's doses on one line, each under its offset from the meal.
 *
 * Four rows of "За 20 мин до еды / За 12 мин до еды / …" said the same thing
 * four times; the offset is a number and reads as one. The meal's doses are
 * selected together because they are judged together.
 */
@Composable
private fun DoseTimeline(
    doses: List<InsulinEvent>,
    mealAt: Instant?,
    zone: TimeZone,
    mealDoses: Set<Int>,
    selection: BolusSelection,
    onSelect: (BolusSelection) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 14.dp)
            .padding(bottom = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        doses.forEachIndexed { index, event ->
            val isMealDose = index in mealDoses
            val selected = when (selection) {
                BolusSelection.Meal -> isMealDose
                is BolusSelection.Dose -> selection.index == index
            }
            val reason = bolusReason(event, mealAt)
            val label = stringResource(R.string.bolus_dose_semantics, units(event.doseUnits), reason)
            Column(
                modifier = Modifier
                    .widthIn(min = 56.dp)
                    .heightIn(min = 44.dp)
                    .clickable(role = Role.Button) {
                        onSelect(if (isMealDose) BolusSelection.Meal else BolusSelection.Dose(index))
                    }
                    .semantics { contentDescription = label; this.selected = selected }
                    .padding(horizontal = 6.dp, vertical = 4.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = doseOffset(event, mealAt, zone),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 10.sp),
                    maxLines = 1,
                )
                Text(
                    text = units(event.doseUnits),
                    color = if (selected) GT.colors.ink else GT.colors.muted,
                    style = GT.type.monoNumber,
                    maxLines = 1,
                )
                // Selection is drawn, not only coloured: an underline under
                // every dose the lower half is explaining.
                Box(
                    modifier = Modifier
                        .padding(top = 3.dp)
                        .width(24.dp)
                        .height(2.dp)
                        .background(if (selected) GT.colors.ink else GT.colors.surface),
                )
            }
        }
    }
}

/** "−20", "0", "+50" minutes from the meal; the clock time without one. */
private fun doseOffset(event: InsulinEvent, mealAt: Instant?, zone: TimeZone): String {
    if (mealAt == null) return clock(event.timestamp, zone)
    val minutes = ((event.timestamp - mealAt).inWholeSeconds / 60.0).roundToInt()
    return when {
        abs(minutes) <= 2 -> "0"
        minutes < 0 -> "−${-minutes}"
        else -> "+$minutes"
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
        state.cob?.let {
            stringResource(
                if (state.cobIsPrior) R.string.bolus_state_cob_prior else R.string.bolus_state_cob,
            ) to grams(it)
        },
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
