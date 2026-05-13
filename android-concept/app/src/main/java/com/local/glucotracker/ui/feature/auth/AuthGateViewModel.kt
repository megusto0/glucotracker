package com.local.glucotracker.ui.feature.auth

import androidx.lifecycle.ViewModel
import com.local.glucotracker.data.auth.AuthRepository
import com.local.glucotracker.data.auth.AuthSession
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import androidx.lifecycle.viewModelScope

sealed interface AuthGateState {
    data object Loading : AuthGateState
    data object SignedOut : AuthGateState
    data class SignedIn(val session: AuthSession) : AuthGateState
}

@HiltViewModel
class AuthGateViewModel @Inject constructor(
    authRepository: AuthRepository,
) : ViewModel() {
    val state: StateFlow<AuthGateState> =
        authRepository.observeSession()
            .map { session ->
                if (session == null) AuthGateState.SignedOut else AuthGateState.SignedIn(session)
            }
            .stateIn(
                scope = viewModelScope,
                started = SharingStarted.WhileSubscribed(5_000),
                initialValue = AuthGateState.Loading,
            )
}
