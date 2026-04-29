import type {
  FoodEpisodeResponse,
  MealResponse,
  TimelineResponse,
} from "../../api/client";

export type FeedItem =
  | { kind: "episode"; id: string; startAt: string; episode: FoodEpisodeResponse }
  | { kind: "meal"; id: string; startAt: string; meal: MealResponse }
  | {
      kind: "insulin";
      id: string;
      startAt: string;
      event: NonNullable<TimelineResponse["ungrouped_insulin"]>[number];
    };

export type DayGroup = {
  key: string;
  label: string;
  items: FeedItem[];
};
