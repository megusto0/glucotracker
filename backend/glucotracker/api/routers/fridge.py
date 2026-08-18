"""Fridge-backed endpoints that GlucoTracker owns.

Stock itself lives in the fridge service; what lives here is the part the phone
needs and the fridge cannot give it — chiefly a picture of a cooked batch,
taken at the counter with the containers still on the scale.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse

from glucotracker.api.dependencies import CurrentUserDep
from glucotracker.api.schemas import MealPrepPhotoResponse
from glucotracker.application.fridge_sync import FridgeIntegrationService
from glucotracker.infra.storage import product_image_store

router = APIRouter(tags=["fridge"])

MEALPREP_IMAGES = "mealprep_images"
IMAGE_RESPONSE_HEADERS = {"Cache-Control": "private, max-age=604800"}


@router.post(
    "/fridge/mealpreps/{batch_id}/photo",
    response_model=MealPrepPhotoResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadMealPrepPhoto",
)
def upload_mealprep_photo(
    batch_id: UUID,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
) -> MealPrepPhotoResponse:
    """Attach a photograph to a cooked batch and to every container of it."""
    service = FridgeIntegrationService()

    # The client holds container ids, because that is what the code on a lid
    # resolves to. A photograph is of the dish, so it is stored on the batch.
    resolved = service.find_batch_for_container(str(batch_id)) or str(batch_id)

    try:
        product_image_store.save_upload(
            UUID(resolved.replace("-", "")),
            file,
            subdir=MEALPREP_IMAGES,
        )
    except product_image_store.ProductImageStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    url = f"/fridge/mealpreps/{resolved}/photo"
    outcome = service.set_batch_image(resolved, url)
    if outcome == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Такой партии нет в холодильнике.",
        )
    if outcome in ("readonly", "unreachable", "error"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "База холодильника недоступна для записи"
                f" ({outcome}). Файл: {service.db_path}"
            ),
        )
    return MealPrepPhotoResponse(batch_id=UUID(resolved.replace("-", "")), url=url)


@router.get(
    "/fridge/mealpreps/{batch_id}/photo",
    operation_id="getMealPrepPhoto",
)
def get_mealprep_photo(batch_id: UUID) -> Response:
    """Stream a batch photograph.

    Unauthenticated on purpose, like the product image route: mobile Coil loads
    it without the session header, and a 401 here is an empty card, not a
    locked one. The id is a random UUID and the file is a picture of dinner.
    """
    try:
        path = product_image_store.get_full_path(batch_id, subdir=MEALPREP_IMAGES)
    except product_image_store.ProductImageStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal prep photo not found.",
        ) from exc
    return FileResponse(
        path,
        media_type=product_image_store.content_type_for_path(path),
        headers=IMAGE_RESPONSE_HEADERS,
    )
