package com.local.glucotracker.data.auth

import java.util.UUID
import kotlinx.datetime.Instant

data class AuthSession(
    val accessToken: String,
    val refreshToken: String,
    val accessExpiresAt: Instant,
    val userId: UUID,
    val role: String,
)

class AuthException(message: String) : Exception(message)
