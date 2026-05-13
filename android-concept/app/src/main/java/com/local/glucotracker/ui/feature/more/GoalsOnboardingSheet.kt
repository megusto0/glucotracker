package com.local.glucotracker.ui.feature.more

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTPrimaryButton

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GoalsOnboardingSheet(
    onDismiss: () -> Unit,
    onSaveGoals: (kcal: Int?, protein: Int?, carbs: Int?, fat: Int?) -> Unit,
    onSkip: () -> Unit,
) {
    var kcal by remember { mutableStateOf("") }
    var protein by remember { mutableStateOf("") }
    var carbs by remember { mutableStateOf("") }
    var fat by remember { mutableStateOf("") }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = GT.colors.surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = stringResource(R.string.goals_onboarding_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            Text(
                text = stringResource(R.string.goals_onboarding_body),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
            GoalInputField(
                label = stringResource(R.string.more_goals_kcal),
                value = kcal,
                onValueChange = { kcal = it },
            )
            GoalInputField(
                label = stringResource(R.string.more_goals_protein),
                value = protein,
                onValueChange = { protein = it },
            )
            GoalInputField(
                label = stringResource(R.string.more_goals_carbs),
                value = carbs,
                onValueChange = { carbs = it },
            )
            GoalInputField(
                label = stringResource(R.string.more_goals_fat),
                value = fat,
                onValueChange = { fat = it },
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                GTPrimaryButton(
                    text = stringResource(R.string.goals_onboarding_done),
                    onClick = {
                        onSaveGoals(
                            kcal.toIntOrNull(),
                            protein.toIntOrNull(),
                            carbs.toIntOrNull(),
                            fat.toIntOrNull(),
                        )
                    },
                )
                GTOutlineButton(
                    text = stringResource(R.string.goals_onboarding_skip),
                    onClick = onSkip,
                )
            }
        }
    }
}

@Composable
private fun GoalInputField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = {
            Text(
                text = label,
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        },
        modifier = Modifier.fillMaxWidth(),
        textStyle = GT.type.monoLabel.copy(color = GT.colors.ink),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        singleLine = true,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = GT.colors.ink,
            unfocusedBorderColor = GT.colors.hairline2,
            cursorColor = GT.colors.ink,
        ),
        shape = GT.shapes.tag,
    )
}
