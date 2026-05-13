describe("Правая панель журнала питания", () => {
  it("выбор записи -> сводка -> редактирование -> KPI", () => {
    cy.visit("/");

    cy.get('[data-testid^="meal-row-"]').first().click();
    cy.get('[data-testid="panel-summary"]').should("be.visible");
    cy.get('[data-testid="panel-source-confidence"]').should("be.visible");

    cy.contains("button", "Название").click();
    cy.get('input[aria-label="Название записи"]').clear().type("Обновленное блюдо");
    cy.contains("button", "Сохранить").click();

    cy.get('[data-testid="kpi-kcal"]').should("be.visible");
    cy.get('[data-testid="kpi-protein"]').should("be.visible");
    cy.get('[data-testid="kpi-carbs"]').should("be.visible");

    cy.get('[data-testid^="meal-row-"]').first().click();
    cy.get('[data-testid="panel-summary"]').should("not.exist");
  });
});
