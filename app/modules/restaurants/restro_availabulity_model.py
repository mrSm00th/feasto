# class RestaurantAvailability(Base):

#     __tablename__ = "restaurant_availability"

#     id: Mapped[uuid.UUID] = mapped_column(
#         Uuid, primary_key=True, default=uuid.uuid4, index=True
#     )

#     restaurant_id: Mapped[uuid.UUID] = mapped_column(
#         ForeignKey("restaurants.id", ondelete="CASCADE"),
#         nullable=False,
#         index=True,
#     )

#     day_of_week: Mapped[DayOfWeek] = mapped_column(
#         Enum(DayOfWeek),
#         nullable=False,
#     )

#     # Null opening/closing means closed all day (use is_available_24=true with None)
#     opening_time: Mapped[time | None] = mapped_column(
#         Time,
#         nullable=True,
#     )

#     closing_time: Mapped[time | None] = mapped_column(
#         Time,
#         nullable=True,
#     )

#     is_open_24_hours: Mapped[bool] = mapped_column(
#         Boolean,
#         default = False,
#     )

#     # Shift 0 = first shift (lunch), shift 1 = second shift (dinner)
#     # is_open_24_hours rows must always be shift_index=0
#     shift_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

#     is_closed: Mapped[bool] = mapped_column(
#         Boolean,
#         default=False,
#     )

#     created_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), default=lambda: datetime.now(UTC)
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True),
#         default=lambda: datetime.now(UTC),
#         onupdate=lambda: datetime.now(UTC),
#     )

#     restaurant: Mapped[Restaurant] = relationship(back_populates="availability")

#     __table_args__ = (

#         Index("ix_availability_lookup", "restaurant_id", "day_of_week"),

#         UniqueConstraint(
#             "restaurant_id",
#             "day_of_week",
#             "shift_index",
#             name="uq_restaurant_day_shift",
#         ),

#         # Can't be closed AND open 24 hours simultaneously
#         CheckConstraint(
#             "NOT (is_closed = 1 AND is_open_24_hours = 1)",
#             name="ck_not_closed_and_24hrs",
#         ),

#         # 24hr days must have NULL times — no ambiguity
#         CheckConstraint(
#             """
#             NOT (
#                 is_open_24_hours = 1
#                 AND (opening_time IS NOT NULL OR closing_time IS NOT NULL)
#             )
#             """,
#             name="ck_24hr_times_must_be_null",
#         ),

#         # 24hr days must always be shift_index=0 — a single shift covers the day
#         CheckConstraint(
#             "NOT (is_open_24_hours = 1 AND shift_index != 0)",
#             name="ck_24hr_shift_must_be_zero",
#         ),

#         # Regular open days must have both times set
#         CheckConstraint(
#             """
#             NOT (
#                 is_closed = 0
#                 AND is_open_24_hours = 0
#                 AND (opening_time IS NULL OR closing_time IS NULL)
#             )
#             """,
#             name="ck_open_days_require_times",
#         ),

#         # Closing must be after opening — NULL-safe (NULL times pass through)
#         CheckConstraint(
#             "closing_time IS NULL OR opening_time IS NULL OR closing_time > opening_time",
#             name="ck_closing_after_opening",
#         ),
#     )

# #  postgres args-
# #     __table_args__ = (
# #     UniqueConstraint(
# #         "restaurant_id", "day_of_week", "shift_index",
# #         name="uq_restaurant_day_shift",
# #     ),
# #     CheckConstraint(
# #         "NOT (is_closed AND is_open_24_hours)",
# #         name="ck_not_closed_and_24hrs",
# #     ),
# #     CheckConstraint(
# #         "NOT (is_open_24_hours AND (opening_time IS NOT NULL OR closing_time IS NOT NULL))",
# #         name="ck_24hr_times_must_be_null",
# #     ),
# #     CheckConstraint(
# #         "NOT (is_open_24_hours AND shift_index != 0)",
# #         name="ck_24hr_shift_must_be_zero",
# #     ),
# #     CheckConstraint(
# #         "NOT (NOT is_closed AND NOT is_open_24_hours AND (opening_time IS NULL OR closing_time IS NULL))",
# #         name="ck_open_days_require_times",
# #     ),
# #     CheckConstraint(
# #         "closing_time IS NULL OR opening_time IS NULL OR closing_time > opening_time",
# #         name="ck_closing_after_opening",
# #     ),
# # )
