export const identitySchema = {
  "fields": [
    {
      "key": "name",
      "label": "Name",
      "maximum": 80,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "nickname",
      "label": "Nickname",
      "maximum": 80,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "nationality",
      "label": "Nationality",
      "maximum": 300,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "region",
      "label": "Region",
      "maximum": 300,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "cv",
      "label": "Relevant project context",
      "maximum": 16000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "skills",
      "label": "Skills",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "interests",
      "label": "Interests",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "cv_notes",
      "label": "Other relevant project context",
      "maximum": 16000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "subject_expertise",
      "label": "Subject expertise",
      "maximum": 4000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "products_built",
      "label": "Products and projects built",
      "maximum": 6000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "source_website",
      "label": "Portfolio or project website",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "personal_offer",
      "label": "What I can offer personally",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "personal_seeking",
      "label": "What I am looking for personally",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "skills_offer_people",
      "label": "Skills I can offer other residents",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "skills_need_people",
      "label": "Skills I need from other residents",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "environment_offer",
      "label": "What I can offer the village",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "environment_need",
      "label": "What I need from the village",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "reciprocity",
      "label": "What I want in return",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    },
    {
      "key": "moral_compass",
      "label": "Guiding moral approach",
      "maximum": 2000,
      "question": "Which approach most often guides your choices when important values conflict?",
      "choices": [
        "I start with rights and principles that should not be violated.",
        "I start with the likely benefits and harms of each choice.",
        "I start with care, relationships, and responsibilities to others.",
        "I start with community commitments and traditions.",
        "I weigh several approaches; it depends on the situation.",
        "I am unsure or still exploring my principles."
      ],
      "private": true
    },
    {
      "key": "political_standing",
      "label": "Political outlook (optional)",
      "maximum": 2000,
      "question": "Which option comes closest to your self-described political outlook? Choose mixed/unrepresented or skip if these labels do not fit your context.",
      "choices": [
        "I identify mainly with progressive or left-leaning politics.",
        "I identify mainly with conservative or right-leaning politics.",
        "I identify mainly with centrist or moderate politics.",
        "I prioritise individual liberty and limited government.",
        "I prioritise ecological politics and environmental responsibility.",
        "My outlook is mixed, context-specific, or not represented here.",
        "I do not identify with a political position or am unsure."
      ],
      "private": true
    },
    {
      "key": "moral_care",
      "label": "Care",
      "maximum": 1200,
      "question": "If a promising project could harm a few people while helping many, how would you decide whether to proceed?",
      "choices": [
        "Do not proceed while people face serious harm, even if many could benefit.",
        "Proceed only with affected people participating in the decision and strong protections.",
        "Proceed if the overall benefits outweigh the harms and those harmed receive support.",
        "It depends on the severity, alternatives, and what affected people want.",
        "I am unsure how I would decide."
      ],
      "private": true
    },
    {
      "key": "moral_equality",
      "label": "Equality",
      "maximum": 1200,
      "question": "When a community has limited resources, what should everyone receive equally, and when might unequal access be justified?",
      "choices": [
        "Give everyone an equal share of the limited resources.",
        "Give more to people with greater needs or fewer alternatives.",
        "Give everyone an equal minimum, then decide how to distribute the rest.",
        "Let the community agree on an allocation for this particular situation.",
        "I am unsure; I would need more context."
      ],
      "private": true
    },
    {
      "key": "moral_proportionality",
      "label": "Proportionality",
      "maximum": 1200,
      "question": "If people contribute different amounts of effort, expertise, or money, how should rewards and responsibilities be shared?",
      "choices": [
        "Share rewards equally, even when contributions differ.",
        "Link rewards mainly to effort and time, including less visible work.",
        "Link rewards mainly to results and the value of contributions.",
        "Use agreed contributions while accounting for different needs and capacities.",
        "I am unsure; I would negotiate the arrangement with those involved."
      ],
      "private": true
    },
    {
      "key": "moral_loyalty",
      "label": "Loyalty",
      "maximum": 1200,
      "question": "If your friends or community support a decision you think is wrong, how would you respond? What would make you speak out?",
      "choices": [
        "Support the group decision despite my disagreement.",
        "Raise concerns privately first while continuing to support the group.",
        "Speak out publicly when I believe the decision causes serious harm.",
        "Prioritise my judgment and leave or oppose the group if necessary.",
        "It depends on the issue and the risks; I am not committed to one response."
      ],
      "private": true
    },
    {
      "key": "moral_authority",
      "label": "Authority",
      "maximum": 1200,
      "question": "When should you follow a leader or community rule, and when should you challenge it? What makes authority legitimate?",
      "choices": [
        "Follow established leaders and rules unless there is clear abuse.",
        "Follow authority when it is accountable and those affected can participate.",
        "Assess each instruction independently and challenge rules I consider unjust.",
        "Prefer shared decisions with minimal hierarchy.",
        "It depends on legitimacy, expertise, and the situation; I am unsure otherwise."
      ],
      "private": true
    },
    {
      "key": "moral_sanctity",
      "label": "Purity / sanctity",
      "maximum": 1200,
      "question": "What, if anything, do you consider sacred or worth protecting from degradation? How would you handle a conflicting community preference?",
      "choices": [
        "Protect sacred traditions or practices even when change would be convenient.",
        "Protect human dignity and bodily integrity as boundaries for community choices.",
        "Protect ecosystems and places I regard as irreplaceable.",
        "Allow people their own sacred commitments, without imposing them on others.",
        "Judge choices by harms and benefits rather than sacred boundaries.",
        "I am unsure or this concern is not central to my outlook."
      ],
      "private": true
    },
    {
      "key": "introduction",
      "label": "Public introduction",
      "maximum": 2000,
      "question": null,
      "choices": null,
      "private": false
    }
  ],
  "pillars": [
    [
      "Name",
      [
        "name",
        "nickname"
      ]
    ],
    [
      "Given identity",
      [
        "nationality",
        "region"
      ]
    ],
    [
      "Skill identity",
      [
        "cv",
        "skills",
        "subject_expertise",
        "products_built",
        "source_website",
        "interests",
        "cv_notes"
      ]
    ],
    [
      "Contribution and reciprocity",
      [
        "personal_offer",
        "personal_seeking",
        "skills_offer_people",
        "skills_need_people",
        "environment_offer",
        "environment_need",
        "reciprocity"
      ]
    ],
    [
      "Moral compass",
      [
        "moral_compass",
        "political_standing",
        "moral_care",
        "moral_equality",
        "moral_proportionality",
        "moral_loyalty",
        "moral_authority",
        "moral_sanctity"
      ]
    ],
    [
      "Public introduction",
      [
        "introduction"
      ]
    ]
  ]
} as const;
