package com.local.glucotracker.ui.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.auth.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class LoginUiState(
    val username: String = "",
    val password: String = "",
    val isLoading: Boolean = false,
    val showInvalidCredentials: Boolean = false,
)

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {
    private val mutableState = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = mutableState

    fun updateUsername(value: String) {
        mutableState.update {
            it.copy(username = value, showInvalidCredentials = false)
        }
    }

    fun updatePassword(value: String) {
        mutableState.update {
            it.copy(password = value, showInvalidCredentials = false)
        }
    }

    fun login() {
        val current = mutableState.value
        if (current.isLoading || current.username.isBlank() || current.password.isBlank()) return

        viewModelScope.launch {
            mutableState.update { it.copy(isLoading = true, showInvalidCredentials = false) }
            val result = authRepository.login(
                username = current.username.trim(),
                password = current.password,
            )
            mutableState.update {
                if (result.isSuccess) {
                    it.copy(isLoading = false, password = "", showInvalidCredentials = false)
                } else {
                    it.copy(isLoading = false, showInvalidCredentials = true)
                }
            }
        }
    }
}
