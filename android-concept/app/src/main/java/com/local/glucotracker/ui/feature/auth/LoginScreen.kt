package com.local.glucotracker.ui.feature.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTPrimaryButton

@Composable
fun LoginRoute(
    viewModel: LoginViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LoginScreen(
        state = state,
        onUsernameChange = viewModel::updateUsername,
        onPasswordChange = viewModel::updatePassword,
        onLogin = viewModel::login,
    )
}

@Composable
fun LoginScreen(
    state: LoginUiState,
    onUsernameChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onLogin: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .padding(horizontal = 22.dp, vertical = 34.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = stringResource(R.string.auth_login_title),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
        )
        Spacer(Modifier.height(22.dp))
        LoginTextField(
            value = state.username,
            onValueChange = onUsernameChange,
            label = stringResource(R.string.auth_username_label),
            keyboardType = KeyboardType.Text,
            imeAction = ImeAction.Next,
        )
        Spacer(Modifier.height(12.dp))
        LoginTextField(
            value = state.password,
            onValueChange = onPasswordChange,
            label = stringResource(R.string.auth_password_label),
            keyboardType = KeyboardType.Password,
            imeAction = ImeAction.Done,
            isPassword = true,
        )
        if (state.showInvalidCredentials) {
            Text(
                text = stringResource(R.string.auth_invalid_credentials),
                color = GT.colors.warn,
                style = GT.type.sansLabel,
                modifier = Modifier.padding(top = 10.dp),
            )
        }
        Spacer(Modifier.height(18.dp))
        GTPrimaryButton(
            text = if (state.isLoading) {
                stringResource(R.string.auth_login_loading)
            } else {
                stringResource(R.string.auth_login_submit)
            },
            onClick = onLogin,
            enabled = !state.isLoading && state.username.isNotBlank() && state.password.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun LoginTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    keyboardType: KeyboardType,
    imeAction: ImeAction,
    modifier: Modifier = Modifier,
    isPassword: Boolean = false,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier.fillMaxWidth(),
        label = {
            Text(
                text = label,
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        },
        textStyle = GT.type.sansBody.copy(color = GT.colors.ink),
        keyboardOptions = KeyboardOptions(
            keyboardType = keyboardType,
            imeAction = imeAction,
        ),
        visualTransformation = if (isPassword) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        singleLine = true,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = GT.colors.ink,
            unfocusedBorderColor = GT.colors.hairline2,
            cursorColor = GT.colors.ink,
        ),
        shape = GT.shapes.card,
    )
}
