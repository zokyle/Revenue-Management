from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.property import Hotel, RoomType
from app.models.forecasts import ForecastRecord, PricingRecommendation
from app.models.costs import CostProfile
from app.models.rates import RatePlan
from app.engine.optimizer import EBITDAOptimizer
from app.schemas.optimization import OptimizationRequest, DisplacementRequest
from app.schemas.forecasts import PricingRecommendationResponse

router = APIRouter()


@router.post("/{hotel_id}/optimize")
def run_optimization(hotel_id: int, data: OptimizationRequest, db: Session = Depends(get_db)):
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    if not hotel:
        raise HTTPException(404, "Hotel not found")

    cost_profile = db.query(CostProfile).filter(CostProfile.hotel_id == hotel_id).first()
    if not cost_profile:
        raise HTTPException(400, "No cost profile configured. Add one in Settings first.")

    room_types = db.query(RoomType).filter(RoomType.hotel_id == hotel_id)
    if data.room_type_id:
        room_types = room_types.filter(RoomType.id == data.room_type_id)
    room_types = room_types.all()

    optimizer = EBITDAOptimizer()
    results = []

    for rt in room_types:
        forecasts = db.query(ForecastRecord).filter(
            ForecastRecord.hotel_id == hotel_id,
            ForecastRecord.room_type_id == rt.id,
            ForecastRecord.forecast_date >= data.start_date,
            ForecastRecord.forecast_date <= data.end_date,
        ).all()

        for forecast in forecasts:
            forecast_dict = {
                "predicted_demand": forecast.predicted_demand,
                "predicted_occupancy": forecast.predicted_occupancy,
            }
            result = optimizer.optimize(
                db=db,
                hotel_id=hotel_id,
                room_type_id=rt.id,
                target_date=forecast.forecast_date,
                forecast=forecast_dict,
                cost_profile=cost_profile,
            )
            if "error" in result:
                continue

            results.append(result)

            # Save pricing recommendation from optimization
            optimal = result["optimal_scenario"]
            current = result["current_scenario"]
            improvement = result["improvement_pct"]

            rec = PricingRecommendation(
                hotel_id=hotel_id,
                room_type_id=rt.id,
                date=forecast.forecast_date,
                recommended_rate=optimal["rate"],
                current_rate=current["rate"],
                expected_occupancy=optimal["demand"] / rt.physical_rooms if rt.physical_rooms > 0 else 0,
                expected_revpar=optimal["rate"] * (optimal["demand"] / rt.physical_rooms) if rt.physical_rooms > 0 else 0,
                expected_ebitda_contribution=optimal["ebitda"],
                status="pending",
                reason_text=f"EBITDA optimization: {improvement:+.1f}% improvement at ${optimal['rate']:.0f} vs ${current['rate']:.0f}",
                generated_at=datetime.utcnow(),
            )
            db.add(rec)

    db.commit()
    return results


@router.get("/{hotel_id}/recommendations", response_model=list[PricingRecommendationResponse])
def get_recommendations(
    hotel_id: int,
    start_date: date = Query(None),
    end_date: date = Query(None),
    status: str = Query("pending"),
    db: Session = Depends(get_db),
):
    query = db.query(PricingRecommendation).filter(
        PricingRecommendation.hotel_id == hotel_id,
    )
    if status:
        query = query.filter(PricingRecommendation.status == status)
    if start_date:
        query = query.filter(PricingRecommendation.date >= start_date)
    if end_date:
        query = query.filter(PricingRecommendation.date <= end_date)
    return query.order_by(PricingRecommendation.date).all()


@router.put("/{hotel_id}/recommendations/{rec_id}/accept")
def accept_recommendation(hotel_id: int, rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(PricingRecommendation).filter(
        PricingRecommendation.id == rec_id,
        PricingRecommendation.hotel_id == hotel_id,
    ).first()
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    rec.status = "accepted"
    db.commit()
    return {"status": "accepted", "id": rec_id}


@router.put("/{hotel_id}/recommendations/{rec_id}/reject")
def reject_recommendation(hotel_id: int, rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(PricingRecommendation).filter(
        PricingRecommendation.id == rec_id,
        PricingRecommendation.hotel_id == hotel_id,
    ).first()
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    rec.status = "rejected"
    db.commit()
    return {"status": "rejected", "id": rec_id}


@router.post("/{hotel_id}/displacement")
def displacement_analysis(hotel_id: int, data: DisplacementRequest, db: Session = Depends(get_db)):
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    if not hotel:
        raise HTTPException(404, "Hotel not found")

    cost_profile = db.query(CostProfile).filter(CostProfile.hotel_id == hotel_id).first()
    cpor = cost_profile.cpor if cost_profile else 45.0

    forecasts = db.query(ForecastRecord).filter(
        ForecastRecord.hotel_id == hotel_id,
        ForecastRecord.room_type_id == data.room_type_id,
        ForecastRecord.forecast_date >= data.check_in,
    ).limit(data.group_nights).all()

    avg_transient_rate = sum(f.predicted_adr or 200 for f in forecasts) / max(len(forecasts), 1)
    avg_occupancy = sum(f.predicted_occupancy for f in forecasts) / max(len(forecasts), 1)

    rt = db.query(RoomType).filter(RoomType.id == data.room_type_id).first()
    available = rt.physical_rooms if rt else 100

    optimizer = EBITDAOptimizer()
    result = optimizer.displacement_analysis(
        group_rooms=data.group_rooms,
        group_rate=data.group_rate,
        group_nights=data.group_nights,
        expected_transient_rate=avg_transient_rate,
        expected_transient_occupancy=avg_occupancy,
        available_rooms=available,
        cpor=cpor,
    )

    recommendation = "ACCEPT" if result["accept"] else "REJECT"
    return {
        "group_value": result["group_value"],
        "displaced_transient_value": result["displaced_transient_value"],
        "net_value": result["net_value"],
        "recommendation": recommendation,
        "details": (
            f"Group contributes ${result['group_value']:,.0f} vs displaced transient "
            f"${result['displaced_transient_value']:,.0f} (net: ${result['net_value']:+,.0f})"
        ),
    }
