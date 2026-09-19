# A virtual wardrobe for Hem

Build a Quest companion that uses the same wardrobe and outfit records as the
messaging service. The initial experience is a room of garment cards: browse your
clothes, grab cards, assemble an outfit on a board, and ask Hem to explain the
combination for an occasion and forecast.

## Suggested implementation

Use Unity with OpenXR and XR Interaction Toolkit. Garment cards can use the
confirmed description and reference photo. XR Grab Interactables support grabbing
and arranging cards, while a world-space UI presents weather, outfit explanations,
source links, and approval requests. Start with a seated or stationary layout.

Place the Unity client under `apps/quest/` when implementation begins. Keep styling,
AI credentials, source retrieval, care rules, and commerce actions on the server.

## Backend contract

For local prototyping with an operator token:

| Operation | Endpoint |
| --- | --- |
| Read wardrobe, outfits and garment attributes | `GET /dev/wardrobe/{user_id}` |
| Retrieve a reference photo | `GET /dev/photos/{user_id}/{asset_id}` |
| Ask for advice with an occasion and date | `POST /dev/chat` |
| Record a wear or approve a prepared request | `POST /dev/chat` with the explicit command |

Send the bearer token in the Authorization header, never a query string. These are
development endpoints; production pairing should exchange a one-time code sent
through the user's verified messaging account for a scoped client session. The
server must derive ownership from that session. Never embed the operator token,
OpenAI key, or Linq key in a distributed headset build.

For free-form outfit assembly, add a server endpoint validating selected garment
IDs, availability, and ownership before saving the selection. Selecting an outfit
in VR should create a suggestion. A separate 'I wore this' action records history.
Approving a service request should remain distinct from external booking/payment.

## Visual fidelity

Wardrobe photos can power reference cards immediately. Accurate avatar try-on,
fabric drape and size prediction require garment segmentation, measurements,
compatible garment meshes, avatar fitting and cloth simulation. Treat generated
visualizations as previews, not fit guarantees. Build browsing and outfit assembly
first, then add garment cutouts and 3D assets as a separate pipeline.

## References

- [Unity XR Interaction Toolkit](https://docs.unity3d.com/Packages/com.unity.xr.interaction.toolkit@3.0/manual/index.html)
- [Unity OpenXR](https://docs.unity3d.com/Packages/com.unity.xr.openxr@1.14/manual/index.html)
