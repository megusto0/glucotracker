package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.data.api.GlucoseApi
import com.local.glucotracker.generated.model.TopUpDoseResponse
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.format.formatMmol
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * "Сколько добавить?" on the phone — the same backend number as the desktop.
 *
 * Nothing is computed here: the follow-up is the smaller of the carb/IOB
 * balance and the history model, decided by `/glucose/top-up-dose`. It needs a
 * live reading, so it is asked for on demand and never cached for offline use.
 */
internal sealed interface TopUpUi {
    data object Idle : TopUpUi
    data object Loading : TopUpUi
    data object Failed : TopUpUi
    data class Result(
        val status: TopUpStatusUi,
        val units: Double?,
        /** Balance terms; present only when the balance is the answer. */
        val carbUnits: Double?,
        val correctionUnits: Double?,
        val iobUnits: Double?,
        /** Present only when the history model is the answer. */
        val modelBalanceUnits: Double?,
        val glucose: Double?,
        val trend30: Double?,
        val target: Double?,
        val cobG: Double?,
        val icr: Double?,
        val isf: Double?,
    ) : TopUpUi
}

internal enum class TopUpStatusUi { Ready, NotNeeded, LowOrFalling, NoIcr, NoGlucose }

internal fun TopUpDoseResponse.toTopUpUi(): TopUpUi.Result {
    val fromModel = limitedBy == TopUpDoseResponse.LimitedBy.MODEL
    return TopUpUi.Result(
        status = when (status) {
            TopUpDoseResponse.Status.READY -> TopUpStatusUi.Ready
            TopUpDoseResponse.Status.NOT_NEEDED -> TopUpStatusUi.NotNeeded
            TopUpDoseResponse.Status.LOW_OR_FALLING -> TopUpStatusUi.LowOrFalling
            TopUpDoseResponse.Status.ICR_UNAVAILABLE -> TopUpStatusUi.NoIcr
            TopUpDoseResponse.Status.GLUCOSE_UNAVAILABLE -> TopUpStatusUi.NoGlucose
        },
        units = units?.toDouble(),
        carbUnits = carbUnits?.toDouble()?.takeUnless { fromModel },
        correctionUnits = correctionUnits?.toDouble()?.takeUnless { fromModel },
        iobUnits = iobUnits?.toDouble()?.takeUnless { fromModel },
        modelBalanceUnits = balanceUnits?.toDouble()?.takeIf { fromModel },
        glucose = glucoseMmolL?.toDouble(),
        trend30 = trendMmolLPer30Min?.toDouble(),
        target = targetMmolL?.toDouble(),
        cobG = cobG?.toDouble(),
        icr = icrGPerUnit?.toDouble(),
        isf = isfMmolLPerUnit?.toDouble(),
    )
}

@HiltViewModel
class TopUpDoseViewModel @Inject constructor(
    private val glucoseApi: GlucoseApi,
) : ViewModel() {
    private val _state = MutableStateFlow<TopUpUi>(TopUpUi.Idle)
    internal val state: StateFlow<TopUpUi> = _state.asStateFlow()

    fun request() {
        if (_state.value == TopUpUi.Loading) return
        _state.value = TopUpUi.Loading
        viewModelScope.launch {
            _state.value = runCatching { glucoseApi.topUpDose().toTopUpUi() }
                .getOrElse { TopUpUi.Failed }
        }
    }
}

@Composable
internal fun TopUpPanel(
    modifier: Modifier = Modifier,
    viewModel: TopUpDoseViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    TopUpContent(state = state, onRequest = viewModel::request, modifier = modifier)
}

/** Stateless body, so a golden can draw each answer. */
@Composable
internal fun TopUpContent(
    state: TopUpUi,
    onRequest: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        GTOutlineButton(
            text = stringResource(
                if (state == TopUpUi.Loading) R.string.topup_loading else R.string.topup_button,
            ),
            onClick = onRequest,
            enabled = state != TopUpUi.Loading,
        )
        when (state) {
            TopUpUi.Idle, TopUpUi.Loading -> Unit
            TopUpUi.Failed -> TopUpNote(stringResource(R.string.bolus_calc_load_error))
            is TopUpUi.Result -> TopUpResult(state)
        }
    }
}

@Composable
private fun TopUpResult(result: TopUpUi.Result) {
    Column(
        modifier = Modifier
            .padding(top = 4.dp)
            .semantics { liveRegion = LiveRegionMode.Polite },
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        when (result.status) {
            TopUpStatusUi.Ready, TopUpStatusUi.NotNeeded -> {
                Text(
                    text = stringResource(R.string.topup_units, units(result.units ?: 0.0)),
                    color = GT.colors.ink,
                    style = GT.type.monoNumber,
                )
                val line = when {
                    result.status == TopUpStatusUi.NotNeeded ->
                        stringResource(R.string.topup_not_needed)
                    result.modelBalanceUnits != null ->
                        stringResource(R.string.bolus_topup_model, units(result.modelBalanceUnits))
                    result.carbUnits != null && result.correctionUnits != null &&
                        result.iobUnits != null ->
                        stringResource(
                            R.string.topup_balance_line,
                            units(result.carbUnits),
                            units(result.correctionUnits),
                            units(result.iobUnits),
                        )
                    else -> null
                }
                line?.let { TopUpNote(it) }
                TopUpContext(result)
            }
            TopUpStatusUi.LowOrFalling -> TopUpNote(stringResource(R.string.topup_low), warn = true)
            TopUpStatusUi.NoIcr -> TopUpNote(stringResource(R.string.topup_no_icr))
            TopUpStatusUi.NoGlucose -> TopUpNote(stringResource(R.string.topup_no_cgm))
        }
    }
}

@Composable
private fun TopUpContext(result: TopUpUi.Result) {
    val glucose = result.glucose ?: return
    val target = result.target ?: return
    val head = formatMmol(glucose) + (
        result.trend30?.let { " " + stringResource(R.string.topup_trend, signedMmol(it)) }
            ?: ""
        )
    Text(
        text = stringResource(
            R.string.topup_context,
            head,
            formatMmol(target),
            (result.cobG ?: 0.0).roundToInt().toString(),
        ),
        color = GT.colors.muted,
        style = GT.type.monoLabel.copy(fontSize = 10.sp),
    )
}

@Composable
private fun TopUpNote(text: String, warn: Boolean = false) {
    Text(
        text = text,
        color = if (warn) GT.colors.warn else GT.colors.ink2,
        style = GT.type.monoLabel.copy(fontSize = 11.sp),
    )
}

private fun units(value: Double): String = "%.1f".format(value).replace('.', ',')

/** Typographic minus, never hyphen-minus (CONCEPT number rules). */
private fun signedMmol(value: Double): String {
    val body = formatMmol(abs(value))
    return when {
        value >= 0.05 -> "+$body"
        value <= -0.05 -> "−$body"
        else -> body
    }
}
