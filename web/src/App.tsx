import { Champions } from "./pages/Champions";
import { CoachPreview } from "./pages/CoachPreview";
import { Overview } from "./pages/Overview";
import { useRoute } from "./router";

export default function App() {
  const route = useRoute();
  switch (route.page) {
    case "champions":
      return <Champions />;
    case "coach":
      return <CoachPreview question={route.params.get("q") ?? ""} />;
    default:
      return <Overview />;
  }
}
