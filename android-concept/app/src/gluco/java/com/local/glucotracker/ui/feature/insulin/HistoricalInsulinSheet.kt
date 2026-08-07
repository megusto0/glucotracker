package com.local.glucotracker.ui.feature.insulin

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.add
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.domain.model.CreateNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.generated.model.InsulinRecommendationResponse
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.glucose.GlucoCardAction
import dagger.hilt.android.lifecycle.HiltViewModel
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.roundToInt
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock

enum class IcrDaypart { Morning, Day, Evening }

/** Why the correction half could not be produced for this episode. */
enum class CorrectionGap {
    TargetRequired,
    IsfUnavailable,
    GlucoseUnavailable,
    TrendUnavailable,
}

/** The correction that turns a food dose into a dose for right now. */
data class CorrectionPart(
    val units: Double,
    val glucoseMmolL: Double?,
    val projectedGlucoseMmolL: Double?,
    val targetMmolL: Double?,
    val isfMmolLPerUnit: Double?,
    val isfIsDefault: Boolean,
    val iobUnits: Double?,
    val excessIobUnits: Double?,
    val projectionIsForecast: Boolean,
)

/** Everything the meal half was derived from, so the sheet can show it. */
data class MealBasis(
    val carbsG: Double,
    val icrGPerUnit: Double?,
    val icrConfiguredGPerUnit: Double?,
    val icrDaypart: IcrDaypart?,
    val icrAfterSleep: Boolean,
    val icrDoseUnits: Double?,
    val historyMedianUnits: Double?,
    val historyWeight: Double?,
    val impliedIcrGPerUnit: Double?,
    val matchedEpisodeCount: Int,
)

sealed interface HistoricalInsulinUiState {
    data object Loading : HistoricalInsulinUiState

    /**
     * The headline is the total whenever the correction could be produced.
     *
     * This surface used to show [mealUnits] alone, which silently dropped the
     * correction and the insulin still working — on a plateau with a few units
     * on board the two differ by several units, in either direction.
     */
    data class Ready(
        val headlineUnits: Double,
        val mealUnits: Double,
        val rangeLowUnits: Double,
        val rangeHighUnits: Double,
        val matchedEpisodeCount: Int,
        val correction: CorrectionPart?,
        val correctionGap: CorrectionGap?,
        val basis: MealBasis,
    ) : HistoricalInsulinUiState {
        val includesCorrection: Boolean get() = correction != null
    }

    data class Unavailable(
        val reason: Reason,
        val matchedEpisodeCount: Int,
    ) : HistoricalInsulinUiState {
        enum class Reason {
            InsufficientHistory,
            MealWithoutCarbs,
            LowOrFalling,
        }
    }

    data object Error : HistoricalInsulinUiState
}

@HiltViewModel
class HistoricalInsulinViewModel @Inject constructor(
    private val glucoseApi: GlucoseApi,
    private val outboxRepository: OutboxRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<HistoricalInsulinUiState>(
        HistoricalInsulinUiState.Loading,
    )
    val state: StateFlow<HistoricalInsulinUiState> = _state
    private var loadedMealIds: List<String>? = null

    fun load(mealIds: List<String>) {
        val normalized = mealIds.distinct()
        if (loadedMealIds == normalized && _state.value !is HistoricalInsulinUiState.Error) return
        loadedMealIds = normalized
        _state.value = HistoricalInsulinUiState.Loading
        viewModelScope.launch {
            val ids = runCatching { normalized.map(UUID::fromString) }
                .getOrElse {
                    if (loadedMealIds == normalized) {
                        _state.value = HistoricalInsulinUiState.Error
                    }
                    return@launch
                }
            val loadedState = runCatching { glucoseApi.insulinRecommendation(ids) }
                .fold(
                    onSuccess = { response -> response.toUiState() },
                    onFailure = { HistoricalInsulinUiState.Error },
                )
            if (loadedMealIds == normalized) {
                _state.value = loadedState
            }
        }
    }

    fun enqueueActual(units: Double, onQueued: () -> Unit) {
        viewModelScope.launch {
            outboxRepository.enqueue(
                CreateNightscoutInsulinOutboxKind(
                    recordedAt = Clock.System.now(),
                    insulinUnits = units,
                    idempotencyKey = UUID.randomUUID().toString(),
                ),
            )
            onQueued()
        }
    }
}

internal fun InsulinRecommendationResponse.toUiState(): HistoricalInsulinUiState =
    when (status) {
        InsulinRecommendationResponse.Status.READY -> {
            val meal = recommendedUnits?.toDouble()
            val low = rangeLowUnits?.toDouble()
            val high = rangeHighUnits?.toDouble()
            if (meal == null || low == null || high == null) {
                HistoricalInsulinUiState.Error
            } else {
                val correction = correctionPart()
                val total = totalRecommendedUnits?.toDouble()
                // The backend only produces a total when the correction is
                // usable. Without one the meal figure still stands, but it must
                // not be presented as if it accounted for glucose and IOB.
                val headline = if (correction != null && total != null) total else meal
                HistoricalInsulinUiState.Ready(
                    headlineUnits = headline,
                    mealUnits = meal,
                    rangeLowUnits = low,
                    rangeHighUnits = high,
                    matchedEpisodeCount = matchedEpisodeCount,
                    correction = correction,
                    correctionGap = if (correction == null) correctionGap() else null,
                    basis = MealBasis(
                        carbsG = targetCarbsG.toDouble(),
                        icrGPerUnit = icrGPerUnit?.toDouble(),
                        icrConfiguredGPerUnit = icrConfiguredGPerUnit?.toDouble(),
                        icrDaypart = when (icrDaypart) {
                            InsulinRecommendationResponse.IcrDaypart.MORNING -> IcrDaypart.Morning
                            InsulinRecommendationResponse.IcrDaypart.DAY -> IcrDaypart.Day
                            InsulinRecommendationResponse.IcrDaypart.EVENING -> IcrDaypart.Evening
                            null -> null
                        },
                        icrAfterSleep = icrAfterSleep == true,
                        icrDoseUnits = icrDoseUnits?.toDouble(),
                        historyMedianUnits = historyMedianUnits?.toDouble(),
                        historyWeight = historyWeight?.toDouble(),
                        impliedIcrGPerUnit = impliedIcrGPerUnit?.toDouble(),
                        matchedEpisodeCount = matchedEpisodeCount,
                    ),
                )
            }
        }
        InsulinRecommendationResponse.Status.INSUFFICIENT_HISTORY ->
            HistoricalInsulinUiState.Unavailable(
                reason = HistoricalInsulinUiState.Unavailable.Reason.InsufficientHistory,
                matchedEpisodeCount = matchedEpisodeCount,
            )
        InsulinRecommendationResponse.Status.MEAL_WITHOUT_CARBS ->
            HistoricalInsulinUiState.Unavailable(
                reason = HistoricalInsulinUiState.Unavailable.Reason.MealWithoutCarbs,
                matchedEpisodeCount = matchedEpisodeCount,
            )
        InsulinRecommendationResponse.Status.LOW_OR_FALLING ->
            HistoricalInsulinUiState.Unavailable(
                reason = HistoricalInsulinUiState.Unavailable.Reason.LowOrFalling,
                matchedEpisodeCount = matchedEpisodeCount,
            )
    }

private fun InsulinRecommendationResponse.correctionPart(): CorrectionPart? {
    val usable = correctionStatus == InsulinRecommendationResponse.CorrectionStatus.READY ||
        correctionStatus == InsulinRecommendationResponse.CorrectionStatus.NOT_NEEDED
    if (!usable) return null
    return CorrectionPart(
        units = correctionUnits?.toDouble() ?: 0.0,
        glucoseMmolL = correctionGlucoseMmolL?.toDouble(),
        projectedGlucoseMmolL = correctionProjectedGlucoseMmolL?.toDouble(),
        targetMmolL = correctionTargetMmolL?.toDouble(),
        isfMmolLPerUnit = correctionIsfMmolLPerUnit?.toDouble(),
        isfIsDefault = correctionIsfSource ==
            InsulinRecommendationResponse.CorrectionIsfSource.DEFAULT,
        iobUnits = correctionIobUnits?.toDouble(),
        excessIobUnits = correctionExcessIobUnits?.toDouble(),
        projectionIsForecast = correctionProjectionSource ==
            InsulinRecommendationResponse.CorrectionProjectionSource.FORECAST,
    )
}

private fun InsulinRecommendationResponse.correctionGap(): CorrectionGap? =
    when (correctionStatus) {
        InsulinRecommendationResponse.CorrectionStatus.TARGET_REQUIRED ->
            CorrectionGap.TargetRequired
        InsulinRecommendationResponse.CorrectionStatus.ISF_UNAVAILABLE ->
            CorrectionGap.IsfUnavailable
        InsulinRecommendationResponse.CorrectionStatus.GLUCOSE_UNAVAILABLE ->
            CorrectionGap.GlucoseUnavailable
        InsulinRecommendationResponse.CorrectionStatus.TREND_UNAVAILABLE ->
            CorrectionGap.TrendUnavailable
        else -> null
    }

/** The sheet without its button, for callers that own their own affordance. */
@Composable
fun HistoricalInsulinSheetHost(
    mealIds: List<String>,
    alreadyGivenUnits: Double,
    onDismiss: () -> Unit,
) {
    if (mealIds.isEmpty()) return
    HistoricalInsulinSheet(
        mealIds = mealIds,
        alreadyGivenUnits = alreadyGivenUnits,
        onDismiss = onDismiss,
    )
}

@Composable
fun HistoricalInsulinButton(
    mealIds: List<String>,
    modifier: Modifier = Modifier,
    alreadyGivenUnits: Double = 0.0,
) {
    if (mealIds.isEmpty()) return
    var showSheet by remember(mealIds) { mutableStateOf(false) }
    // Once insulin exists the calculation is no longer something to act on, but
    // it is still the only way to see whether the dose matched the food.
    val hasInsulin = alreadyGivenUnits > 0.0
    GlucoCardAction(
        text = stringResource(
            if (hasInsulin) {
                R.string.insulin_history_button_compare
            } else {
                R.string.insulin_history_button
            },
        ),
        onClick = { showSheet = true },
        modifier = modifier,
    )
    if (showSheet) {
        HistoricalInsulinSheet(
            mealIds = mealIds,
            alreadyGivenUnits = alreadyGivenUnits,
            onDismiss = { showSheet = false },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HistoricalInsulinSheet(
    mealIds: List<String>,
    alreadyGivenUnits: Double,
    onDismiss: () -> Unit,
    viewModel: HistoricalInsulinViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var valueText by remember(mealIds) { mutableStateOf("") }
    val parsedValue = valueText.replace(',', '.').toDoubleOrNull()
        ?.takeIf { it > 0.0 && it <= 100.0 }

    LaunchedEffect(mealIds) {
        viewModel.load(mealIds)
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = false),
        containerColor = GT.colors.bg,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
        scrimColor = GT.colors.ink.copy(alpha = 0.55f),
        contentWindowInsets = { WindowInsets.ime.add(WindowInsets.navigationBars) },
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .imePadding()
                .padding(horizontal = 18.dp, vertical = 18.dp)
                .testTag("historical-insulin-sheet"),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = stringResource(R.string.insulin_history_title),
                    color = GT.colors.ink,
                    style = GT.type.serifSection,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.weight(1f))
                Text(
                    text = stringResource(R.string.insulin_entry_cancel),
                    modifier = Modifier
                        .heightIn(min = 44.dp)
                        .clickable(onClick = onDismiss)
                        .padding(horizontal = 4.dp, vertical = 12.dp),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                )
            }

            HistoricalEstimateBlock(
                state = state,
                alreadyGivenUnits = alreadyGivenUnits,
            )

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(GT.colors.surface, GT.shapes.card)
                    .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
                    .padding(14.dp),
            ) {
                Text(
                    text = stringResource(R.string.insulin_actual_title),
                    color = GT.colors.ink2,
                    style = GT.type.sansLabel,
                )
                Row(
                    modifier = Modifier.padding(top = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    BasicTextField(
                        value = valueText,
                        onValueChange = { valueText = sanitizeUnitsInput(it) },
                        modifier = Modifier
                            .weight(1f)
                            .height(54.dp)
                            .background(GT.colors.surface2, GT.shapes.card)
                            .border(
                                GT.space.hairline,
                                GT.colors.hairline2,
                                GT.shapes.card,
                            )
                            .padding(horizontal = 14.dp),
                        textStyle = GT.type.monoNumber.copy(color = GT.colors.ink),
                        cursorBrush = SolidColor(GT.colors.ink),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Decimal,
                            imeAction = ImeAction.Done,
                        ),
                        keyboardActions = KeyboardActions(
                            onDone = {
                                parsedValue?.let { units ->
                                    viewModel.enqueueActual(units, onDismiss)
                                }
                            },
                        ),
                        decorationBox = { inner ->
                            Box(contentAlignment = Alignment.CenterStart) {
                                if (valueText.isBlank()) {
                                    Text(
                                        text = stringResource(R.string.insulin_entry_placeholder),
                                        color = GT.colors.muted,
                                        style = GT.type.monoNumber,
                                    )
                                }
                                inner()
                            }
                        },
                    )
                    Text(
                        text = stringResource(R.string.insulin_entry_label),
                        color = GT.colors.muted,
                        style = GT.type.kicker,
                    )
                }
                GTOutlineButton(
                    text = stringResource(R.string.insulin_actual_submit),
                    enabled = parsedValue != null,
                    onClick = {
                        parsedValue?.let { units ->
                            viewModel.enqueueActual(units, onDismiss)
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp),
                )
            }
        }
    }
}

@Composable
private fun HistoricalEstimateBlock(
    state: HistoricalInsulinUiState,
    alreadyGivenUnits: Double,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .padding(14.dp),
    ) {
        Text(
            text = stringResource(R.string.insulin_history_estimate_label),
            color = GT.colors.muted,
            style = GT.type.kicker,
        )
        when (state) {
            HistoricalInsulinUiState.Loading -> Text(
                text = stringResource(R.string.insulin_history_loading),
                modifier = Modifier.padding(top = 8.dp),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
            is HistoricalInsulinUiState.Ready -> {
                Text(
                    text = stringResource(
                        R.string.insulin_history_units_value,
                        formatDose(state.headlineUnits),
                    ),
                    modifier = Modifier
                        .padding(top = 6.dp)
                        .testTag("historical-insulin-total"),
                    color = GT.colors.ink,
                    style = GT.type.monoNumber,
                )
                DoseBreakdown(state)
                IcrLine(state.basis)
                Text(
                    text = stringResource(
                        R.string.insulin_history_range,
                        formatDose(state.rangeLowUnits),
                        formatDose(state.rangeHighUnits),
                        state.matchedEpisodeCount,
                    ),
                    modifier = Modifier.padding(top = 4.dp),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                )
                ReasoningBlock(state)
            }
            is HistoricalInsulinUiState.Unavailable -> Text(
                text = when (state.reason) {
                    HistoricalInsulinUiState.Unavailable.Reason.InsufficientHistory ->
                        stringResource(
                            R.string.insulin_history_insufficient,
                            state.matchedEpisodeCount,
                        )
                    HistoricalInsulinUiState.Unavailable.Reason.MealWithoutCarbs ->
                        stringResource(R.string.insulin_history_no_carbs)
                    HistoricalInsulinUiState.Unavailable.Reason.LowOrFalling ->
                        stringResource(R.string.insulin_history_low_or_falling)
                },
                modifier = Modifier.padding(top = 8.dp),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
            HistoricalInsulinUiState.Error -> Text(
                text = stringResource(R.string.insulin_history_error),
                modifier = Modifier.padding(top = 8.dp),
                color = GT.colors.warn,
                style = GT.type.sansBody,
            )
        }
        Text(
            text = stringResource(R.string.insulin_history_limits),
            modifier = Modifier.padding(top = 10.dp),
            color = GT.colors.muted,
            style = GT.type.sansLabel,
        )
    }
}

/**
 * One term per line, each next to its own number.
 *
 * This was a single line reading «еда 5,8 +0 коррекция −1,3 активный инсулин =
 * 4,5 ЕД», where the signs belong to the values and the labels sit between
 * them, so nothing could be told apart or checked. The same terms stacked read
 * as arithmetic, which is what they are.
 */
@Composable
private fun DoseBreakdown(state: HistoricalInsulinUiState.Ready) {
    val correction = state.correction
    // Insulin still working is subtracted from the total, but only when the
    // correction itself already floored at zero. Leaving it out of the line
    // published arithmetic that does not hold: a 4,9 U meal with no correction
    // summing to 0. Shown here, not only under "Как посчитано", because this
    // is the line that states the total.
    val surplus = correction
        ?.excessIobUnits
        ?.takeIf { it > 0.0 && correction.units <= 0.0 }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .testTag("historical-insulin-breakdown"),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        DoseTermRow(
            label = stringResource(R.string.insulin_term_meal),
            value = formatDose(state.mealUnits),
        )
        correction?.let {
            DoseTermRow(
                label = stringResource(R.string.bolus_term_correction),
                value = formatSignedDose(it.units),
            )
        }
        surplus?.let {
            DoseTermRow(
                label = stringResource(R.string.bolus_term_iob),
                value = "−" + formatDose(it),
            )
        }
        GTHairlineDivider()
        DoseTermRow(
            label = stringResource(R.string.insulin_term_total),
            value = formatDose(state.headlineUnits) + " " +
                stringResource(R.string.insulin_units_short),
            emphasised = true,
        )
    }
    state.correctionGap?.let { gap ->
        Text(
            text = stringResource(
                when (gap) {
                    CorrectionGap.TargetRequired -> R.string.insulin_history_gap_target
                    CorrectionGap.IsfUnavailable -> R.string.insulin_history_gap_isf
                    CorrectionGap.GlucoseUnavailable -> R.string.insulin_history_gap_glucose
                    CorrectionGap.TrendUnavailable -> R.string.insulin_history_gap_trend
                },
            ),
            modifier = Modifier.padding(top = 4.dp),
            color = GT.colors.warn,
            style = GT.type.sansLabel,
        )
    }
}

@Composable
private fun DoseTermRow(label: String, value: String, emphasised: Boolean = false) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            modifier = Modifier.weight(1f),
            color = if (emphasised) GT.colors.ink else GT.colors.ink2,
            style = GT.type.sansLabel,
            maxLines = 1,
        )
        Text(
            text = value,
            color = if (emphasised) GT.colors.ink else GT.colors.ink2,
            style = if (emphasised) GT.type.monoNumber else GT.type.monoLabel,
            maxLines = 1,
        )
    }
}

/** The carbohydrate ratio behind the food half, and what it worked out to. */
@Composable
private fun IcrLine(basis: MealBasis) {
    val ratio = basis.icrGPerUnit ?: basis.impliedIcrGPerUnit ?: return
    val daypart = basis.icrDaypart?.let {
        stringResource(
            when (it) {
                IcrDaypart.Morning -> R.string.insulin_history_daypart_morning
                IcrDaypart.Day -> R.string.insulin_history_daypart_day
                IcrDaypart.Evening -> R.string.insulin_history_daypart_evening
            },
        )
    }
    val base = if (daypart != null) {
        stringResource(R.string.insulin_history_icr_with_daypart, formatRatio(ratio), daypart)
    } else {
        stringResource(R.string.insulin_history_icr, formatRatio(ratio))
    }
    val suffix = when {
        basis.icrAfterSleep && basis.icrConfiguredGPerUnit != null -> stringResource(
            R.string.insulin_history_icr_after_sleep,
            formatRatio(basis.icrConfiguredGPerUnit),
        )
        basis.impliedIcrGPerUnit != null && basis.icrGPerUnit != null ->
            stringResource(
                R.string.insulin_history_icr_implied,
                formatRatio(basis.impliedIcrGPerUnit),
            )
        else -> null
    }
    Text(
        text = if (suffix != null) "$base · $suffix" else base,
        modifier = Modifier
            .padding(top = 4.dp)
            .testTag("historical-insulin-icr"),
        color = GT.colors.ink2,
        style = GT.type.monoLabel,
    )
}

/**
 * The working, folded away by default.
 *
 * A dose the user cannot check is a dose they have to take on trust, and this
 * one is a blend of two estimators plus a correction. Every line here is a step
 * that actually ran, in the order it ran.
 */
@Composable
private fun ReasoningBlock(state: HistoricalInsulinUiState.Ready) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val lines = reasoningLines(state)
    if (lines.isEmpty()) return
    Text(
        text = stringResource(
            if (expanded) {
                R.string.insulin_history_reasoning_hide
            } else {
                R.string.insulin_history_reasoning_show
            },
        ),
        modifier = Modifier
            .heightIn(min = 44.dp)
            .clickable { expanded = !expanded }
            .padding(top = 12.dp, bottom = 4.dp)
            .testTag("historical-insulin-reasoning-toggle"),
        color = GT.colors.accent,
        style = GT.type.sansLabel,
    )
    if (expanded) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .testTag("historical-insulin-reasoning"),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            lines.forEach { line ->
                Text(
                    text = line,
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                )
            }
        }
    }
}

@Composable
private fun reasoningLines(state: HistoricalInsulinUiState.Ready): List<String> {
    val basis = state.basis
    val lines = mutableListOf<String>()
    lines += stringResource(R.string.insulin_history_why_carbs, formatDose(basis.carbsG))
    if (basis.icrDoseUnits != null && basis.icrGPerUnit != null) {
        lines += stringResource(
            R.string.insulin_history_why_icr,
            formatDose(basis.carbsG),
            formatRatio(basis.icrGPerUnit),
            formatDose(basis.icrDoseUnits),
        )
    }
    if (basis.historyMedianUnits != null) {
        lines += stringResource(
            R.string.insulin_history_why_history,
            formatDose(basis.historyMedianUnits),
            basis.matchedEpisodeCount,
        )
    }
    val weight = basis.historyWeight
    if (weight != null && basis.historyMedianUnits != null && basis.icrDoseUnits != null) {
        lines += stringResource(
            R.string.insulin_history_why_blend,
            (weight * 100).roundToInt(),
            ((1.0 - weight) * 100).roundToInt(),
            formatDose(state.mealUnits),
        )
    }
    state.correction?.let { correction ->
        val glucose = correction.glucoseMmolL
        val projected = correction.projectedGlucoseMmolL
        val target = correction.targetMmolL
        val isf = correction.isfMmolLPerUnit
        if (glucose != null && projected != null && target != null && isf != null) {
            lines += stringResource(
                if (correction.projectionIsForecast) {
                    R.string.insulin_history_why_correction_forecast
                } else {
                    R.string.insulin_history_why_correction_trend
                },
                formatMmol(glucose),
                formatMmol(projected),
                formatMmol(target),
                formatMmol(isf),
            )
        }
        correction.iobUnits?.takeIf { it > 0.0 }?.let { iob ->
            lines += stringResource(R.string.insulin_history_why_iob, formatDose(iob))
        }
        correction.excessIobUnits?.takeIf { it > 0.0 && correction.units <= 0.0 }?.let { excess ->
            lines += stringResource(R.string.insulin_history_why_excess_iob, formatDose(excess))
        }
        if (correction.isfIsDefault) {
            lines += stringResource(R.string.insulin_history_why_isf_default)
        }
    }
    return lines
}

private fun formatDose(value: Double): String = decimal("0.#").format(value)

private fun formatRatio(value: Double): String = decimal("0.#").format(value)

private fun formatMmol(value: Double): String = decimal("0.0").format(value)

private fun formatSignedDose(value: Double): String {
    // Typographical minus, per the number formatting rules.
    val formatted = decimal("0.#").format(kotlin.math.abs(value))
    return if (value < 0) "−$formatted" else "+$formatted"
}

private fun decimal(pattern: String): DecimalFormat {
    val symbols = DecimalFormatSymbols(Locale("ru")).apply {
        decimalSeparator = ','
    }
    return DecimalFormat(pattern, symbols)
}
