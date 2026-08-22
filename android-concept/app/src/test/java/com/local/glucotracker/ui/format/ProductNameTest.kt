package com.local.glucotracker.ui.format

import kotlin.test.Test
import kotlin.test.assertEquals

class ProductNameTest {
    @Test
    fun theMultipackThatStartedThisIsTrimmed() {
        // Half a doughnut was logged and the row read like a whole two-pack.
        assertEquals(
            "Пончики Перекрёсток Берлинские с кремом",
            productNameWithoutPack("Пончики Перекрёсток Берлинские с кремом 2x64 г"),
        )
    }

    @Test
    fun plainPackageSizesGoToo() {
        assertEquals("Халва Восточный гость", productNameWithoutPack("Халва Восточный гость 500 г"))
        assertEquals("Напиток Добрый Кола без сахара", productNameWithoutPack("Напиток Добрый Кола без сахара 1 л"))
        assertEquals("Кефир 1% Магнит Свежесть", productNameWithoutPack("Кефир 1% Магнит Свежесть 900 г"))
        assertEquals("Крупа Увелка Гречневая ядрица Экстра", productNameWithoutPack("Крупа Увелка Гречневая ядрица Экстра 5пак*80г"))
    }

    @Test
    fun aSizeInsideTheNameIsLoadBearingAndStays() {
        // «Твикс Экстра 82 г с карамелью» is not «Твикс Экстра».
        assertEquals(
            "Сыр полутвердый Брест-Литовск Королевский 45%",
            productNameWithoutPack("Сыр полутвердый Брест-Литовск Королевский 45% 200 г"),
        )
        assertEquals(
            "Йогурт Epica Ананас 4.8% 130 г с ананасом",
            productNameWithoutPack("Йогурт Epica Ананас 4.8% 130 г с ананасом"),
        )
    }

    @Test
    fun aNameThatIsNothingButItsSizeKeepsIt() {
        // Better a name that repeats the size than no name at all.
        assertEquals("500 г", productNameWithoutPack("500 г"))
    }

    @Test
    fun aPieceCountIsNotPackagingAndStays() {
        // «Наггетсы (9 Шт)» and «Крылышки (6 Шт)» are different dishes; trim
        // the number and two rows claim to be the same thing.
        assertEquals("Наггетсы (9 Шт)", productNameWithoutPack("Наггетсы (9 Шт)"))
        assertEquals("Крылышки (6 Шт)", productNameWithoutPack("Крылышки (6 Шт)"))
        assertEquals("Стрипсы (3 Шт)", productNameWithoutPack("Стрипсы (3 Шт)"))
    }

    @Test
    fun namesWithoutAPackAreUntouched() {
        assertEquals("Сметанник", productNameWithoutPack("Сметанник"))
        assertEquals("Азу с чечевицей", productNameWithoutPack("Азу с чечевицей"))
        assertEquals("Яблоки свежие", productNameWithoutPack("Яблоки свежие"))
    }
}
