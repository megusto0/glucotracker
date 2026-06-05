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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.CreateNightscoutInsulinOutboxKind
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import dagger.hilt.android.lifecycle.HiltViewModel
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock

@Composable
fun InsulinEntryRoute(
    onClose: () -> Unit,
    viewModel: InsulinEntryViewModel = hiltViewModel(),
) {
    InsulinEntrySheet(
        onDismiss = onClose,
        onSubmit = { units ->
            viewModel.enqueue(units, onQueued = onClose)
        },
    )
}

@HiltViewModel
class InsulinEntryViewModel @Inject constructor(
    private val outboxRepository: OutboxRepository,
) : ViewModel() {
    fun enqueue(units: Double, onQueued: () -> Unit) {
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun InsulinEntrySheet(
    onDismiss: () -> Unit,
    onSubmit: (Double) -> Unit,
) {
    var valueText by remember { mutableStateOf("") }
    val focusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current
    val parsedValue = valueText.replace(',', '.').toDoubleOrNull()
        ?.takeIf { it > 0.0 && it <= 100.0 }

    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
        keyboardController?.show()
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
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
                .padding(horizontal = 18.dp, vertical = 20.dp)
                .testTag("insulin-entry-sheet"),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.insulin_entry_title),
                    color = GT.colors.ink,
                    style = GT.type.serifSection,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.weight(1f))
                Text(
                    text = stringResource(R.string.insulin_entry_cancel),
                    modifier = Modifier.clickable(onClick = onDismiss),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel,
                    maxLines = 1,
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 18.dp),
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                BasicTextField(
                    value = valueText,
                    onValueChange = { valueText = sanitizeUnitsInput(it) },
                    modifier = Modifier
                        .weight(1f)
                        .height(64.dp)
                        .focusRequester(focusRequester)
                        .background(GT.colors.surface2, GT.shapes.card)
                        .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.card)
                        .padding(horizontal = 14.dp),
                    textStyle = GT.type.monoNumber.copy(
                        color = GT.colors.ink,
                        textAlign = TextAlign.Start,
                    ),
                    cursorBrush = SolidColor(GT.colors.ink),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Decimal,
                        imeAction = ImeAction.Done,
                    ),
                    keyboardActions = KeyboardActions(
                        onDone = { parsedValue?.let(onSubmit) },
                    ),
                    decorationBox = { inner ->
                        Box(contentAlignment = Alignment.CenterStart) {
                            if (valueText.isBlank()) {
                                Text(
                                    text = stringResource(R.string.insulin_entry_placeholder),
                                    color = GT.colors.muted,
                                    style = GT.type.monoNumber,
                                    maxLines = 1,
                                )
                            }
                            inner()
                        }
                    },
                )
                Text(
                    text = stringResource(R.string.insulin_entry_label),
                    modifier = Modifier.padding(bottom = 12.dp),
                    color = GT.colors.muted,
                    style = GT.type.kicker,
                    maxLines = 1,
                )
            }
            GTOutlineButton(
                text = stringResource(R.string.insulin_entry_submit),
                enabled = parsedValue != null,
                onClick = { parsedValue?.let(onSubmit) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 14.dp),
            )
        }
    }
}

private fun sanitizeUnitsInput(raw: String): String {
    var hasSeparator = false
    val cleaned = buildString {
        raw.forEach { char ->
            when {
                char.isDigit() -> append(char)
                (char == ',' || char == '.') && !hasSeparator -> {
                    append(',')
                    hasSeparator = true
                }
            }
        }
    }
    return cleaned.take(6)
}
