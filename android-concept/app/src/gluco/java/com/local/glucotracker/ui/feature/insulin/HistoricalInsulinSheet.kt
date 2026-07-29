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
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import dagger.hilt.android.lifecycle.HiltViewModel
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock

sealed interface HistoricalInsulinUiState {
    data object Loading : HistoricalInsulinUiState

    data class Ready(
        val recommendedUnits: Double,
        val rangeLowUnits: Double,
        val rangeHighUnits: Double,
        val matchedEpisodeCount: Int,
    ) : HistoricalInsulinUiState

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

private fun InsulinRecommendationResponse.toUiState(): HistoricalInsulinUiState =
    when (status) {
        InsulinRecommendationResponse.Status.READY -> {
            val recommendation = recommendedUnits?.toDouble()
            val low = rangeLowUnits?.toDouble()
            val high = rangeHighUnits?.toDouble()
            if (recommendation == null || low == null || high == null) {
                HistoricalInsulinUiState.Error
            } else {
                HistoricalInsulinUiState.Ready(
                    recommendedUnits = recommendation,
                    rangeLowUnits = low,
                    rangeHighUnits = high,
                    matchedEpisodeCount = matchedEpisodeCount,
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

@Composable
fun HistoricalInsulinButton(
    mealIds: List<String>,
    modifier: Modifier = Modifier,
) {
    if (mealIds.isEmpty()) return
    var showSheet by remember(mealIds) { mutableStateOf(false) }
    GTOutlineButton(
        text = stringResource(R.string.insulin_history_button),
        onClick = { showSheet = true },
        modifier = modifier,
    )
    if (showSheet) {
        HistoricalInsulinSheet(
            mealIds = mealIds,
            onDismiss = { showSheet = false },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HistoricalInsulinSheet(
    mealIds: List<String>,
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

            HistoricalEstimateBlock(state = state)

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
private fun HistoricalEstimateBlock(state: HistoricalInsulinUiState) {
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
                        formatDose(state.recommendedUnits),
                    ),
                    modifier = Modifier.padding(top = 6.dp),
                    color = GT.colors.ink,
                    style = GT.type.monoNumber,
                )
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

private fun formatDose(value: Double): String {
    val symbols = DecimalFormatSymbols(Locale("ru")).apply {
        decimalSeparator = ','
    }
    return DecimalFormat("0.#", symbols).format(value)
}
